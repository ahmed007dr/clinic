"""What can be booked online, where, with whom, and for how much (docs/15, D9).

    Service            defined once for the group
      → BranchService  management's switch: is it offered (and bookable online) in this clinic
        → DoctorServiceRate   which doctor delivers it there, and at what price

A (clinic, doctor, service) is **bookable** only when all of these hold:

* the clinic is running and shown on the public page (`is_active`, `about_visible`);
* the service is active, and its `BranchService` for that clinic is active and
  `online_bookable` — a doctor's contract alone never makes a clinic offer it;
* the doctor is a Doctor, has agreed to be shown (`show_publicly`), has a login
  that management has not stopped, and works in that clinic (home or visiting);
* the doctor has an active contract line for the service, with a valid price —
  the contract's, else the catalogue price, never zero — unless the service is
  priced "after the doctor's evaluation", in which case there is no figure to
  hold to.

This one function decides it. The public catalogue reads it to list services,
clinics and doctors, and booking re-asks it before creating anything
(`resolve_offering`), so what a customer is shown and what the server accepts
cannot drift apart. Everything is read inside the group's tenant context.
"""

from dataclasses import dataclass
from decimal import Decimal

from billing.models import DoctorServiceRate
from billing.pricing import price_from_rate

from .models import BranchService, Service


@dataclass(frozen=True)
class Offering:
    branch: object
    doctor: object
    service: object
    #: The price the customer will be held to, or None when it is set after the
    #: doctor's evaluation.
    price: Decimal | None


def price_is_valid(service, price):
    if service.price_display == Service.PriceDisplay.AFTER_EVALUATION:
        return True
    return price is not None and price > 0


def _shown_branches_of(doctor):
    return {doctor.branch_id, *(branch.pk for branch in doctor.extra_branches.all())}


def qualified_pairs(*, service_ids=None, branch_ids=None, doctor=None):
    """`[(branch id, contract line)]` for every doctor contract that could be
    booked — **ignoring** `BranchService`. The staff screen uses it to say "a
    doctor is ready for this service here"; `offerings` joins it with what
    management switched on."""
    rates = (
        DoctorServiceRate.objects.filter(
            is_active=True, service__is_active=True,
            doctor__employee_type__name="Doctor", doctor__show_publicly=True,
        )
        .exclude(doctor__user_account__is_active=False)
        .select_related("doctor", "service", "service__specialization")
        .prefetch_related("doctor__extra_branches", "doctor__specializations")
    )
    if service_ids is not None:
        rates = rates.filter(service_id__in=service_ids)
    if doctor is not None:
        rates = rates.filter(doctor=doctor)
    pairs = []
    for rate in rates:
        if not price_is_valid(rate.service, price_from_rate(rate, rate.service)):
            continue
        for branch_id in _shown_branches_of(rate.doctor):
            if branch_ids is None or branch_id in branch_ids:
                pairs.append((branch_id, rate))
    return pairs


def offerings(*, service=None, branch=None, doctor=None):
    """Every bookable (clinic, doctor, service), narrowed by whichever of
    `service`, `branch`, `doctor` is given. A handful of queries, whatever the
    size of the group."""
    enabled = BranchService.objects.filter(
        is_active=True, online_bookable=True, service__is_active=True,
        branch__is_active=True, branch__about_visible=True,
    ).select_related("branch", "service", "service__specialization")
    if service is not None:
        enabled = enabled.filter(service=service)
    if branch is not None:
        enabled = enabled.filter(branch=branch)
    enabled = list(enabled)
    if not enabled:
        return []

    switched_on = {(row.branch_id, row.service_id): row for row in enabled}
    found = []
    pairs = qualified_pairs(
        service_ids={row.service_id for row in enabled},
        branch_ids={row.branch_id for row in enabled},
        doctor=doctor,
    )
    for branch_id, rate in pairs:
        row = switched_on.get((branch_id, rate.service_id))
        if row is None:
            continue
        price = price_from_rate(rate, rate.service)
        found.append(Offering(
            branch=row.branch, doctor=rate.doctor, service=rate.service,
            price=None if rate.service.price_display == Service.PriceDisplay.AFTER_EVALUATION else price,
        ))
    return found


def resolve_offering(branch, doctor, service):
    """The `Offering` for this exact choice, or None when it cannot be booked.
    The server's own answer, whatever the client says it was shown."""
    if branch is None or doctor is None or service is None:
        return None
    found = offerings(service=service, branch=branch, doctor=doctor)
    return found[0] if found else None
