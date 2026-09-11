"""What a service costs, and who may say otherwise.

The group owner's rule (2026-09-11): prices come from the doctor's contract
(billing.DoctorServiceRate), set by management; a doctor or receptionist
never types one. Only an Admin or the Owner may set a different price or a
discount. Every screen that records a price — bookings, procedures, treatment
sessions; API and older forms alike — goes through `enforce`.
"""

from decimal import Decimal

from accounts.roles import is_clinic_admin, is_doctor

ZERO = Decimal("0")


def rate_for(doctor, service):
    """The active contract line for this doctor and service, or None."""
    if doctor is None or service is None:
        return None
    from .models import DoctorServiceRate

    return DoctorServiceRate.all_objects.filter(
        tenant_id=service.tenant_id, doctor=doctor, service=service, is_active=True
    ).first()


def price_for(doctor, service):
    """The contract price, else the catalogue price, else None."""
    rate = rate_for(doctor, service)
    if rate is not None and rate.price is not None:
        return rate.price
    return service.base_price if service is not None else None


def percent_for(doctor, service):
    """The doctor's share of what is paid: the contract line's, else the
    doctor's default, else None (nothing agreed — nothing accrues)."""
    if doctor is None:
        return None
    rate = rate_for(doctor, service)
    if rate is not None and rate.commission_percent is not None:
        return rate.commission_percent
    return doctor.commission_percent


def enforce(record, user, *, price_field, discount_field=None, doctor=None, service=None, previous=None):
    """Set `record`'s price from the contract unless `user` is management.

    `previous` is the record as it was before this edit (None on create): for
    someone who may not set prices, an edit that changes neither doctor nor
    service keeps the price it had, rather than repricing an old booking
    because the contract moved on since.
    """
    if is_clinic_admin(user):
        return
    unchanged = previous is not None and (
        getattr(previous, "doctor_id", None) == getattr(doctor, "pk", None)
        and getattr(previous, "service_id", None) == getattr(service, "pk", None)
    )
    if unchanged:
        setattr(record, price_field, getattr(previous, price_field))
    else:
        setattr(record, price_field, price_for(doctor, service) or ZERO)
    if discount_field:
        setattr(record, discount_field, getattr(previous, discount_field) if previous is not None else ZERO)


def enforce_attrs(attrs, user, instance, *, price_field, discount_field=None):
    """The same rule for a DRF serializer's validated data.

    For someone who may not set prices: whatever price or discount was sent is
    discarded; a new record, or one whose doctor or service changes, gets the
    contract price and no discount; otherwise the stored figures stand.
    """
    if is_clinic_admin(user):
        return attrs
    attrs.pop(price_field, None)
    if discount_field:
        attrs.pop(discount_field, None)
    doctor = attrs.get("doctor", getattr(instance, "doctor", None))
    if is_doctor(user) and getattr(user, "employee", None) is not None:
        # A doctor's record is signed with their own name at save time
        # (api/viewsets.py); price it with the same doctor.
        doctor = user.employee
    service = attrs.get("service", getattr(instance, "service", None))
    changed = instance is None or (
        getattr(instance, "doctor_id", None) != getattr(doctor, "pk", None)
        or getattr(instance, "service_id", None) != getattr(service, "pk", None)
    )
    if changed:
        attrs[price_field] = price_for(doctor, service) or ZERO
        if discount_field and instance is None:
            attrs[discount_field] = ZERO
    return attrs
