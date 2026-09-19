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


def price_from_rate(rate, service):
    """The price a contract line sets, else the catalogue price, else None.
    For callers that already hold the line (a listing of many): the same rule
    as `price_for`, without a query per doctor."""
    if rate is not None and rate.price is not None:
        return rate.price
    return service.base_price if service is not None else None


def price_for(doctor, service):
    """The contract price, else the catalogue price, else None."""
    return price_from_rate(rate_for(doctor, service), service)


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


# ------------------------------------------------------------------ quantity

CENT = Decimal("0.01")


def quantity_total(unit_price, quantity):
    """Unit price × quantity, to the cent."""
    return (Decimal(unit_price or 0) * Decimal(quantity or 0)).quantize(CENT)


def quantity_problem(service, quantity):
    """Why `quantity` is not acceptable for `service`, or None.

    Only a service that `requires_quantity` takes one; the Owner or an Admin
    sets the smallest and (optionally) the largest a booking may ask for.
    """
    if service is None or not service.requires_quantity:
        return None
    unit = f" {service.quantity_unit}" if service.quantity_unit else ""
    if quantity is None:
        return f"حدد الكمية{f' ({service.quantity_unit})' if service.quantity_unit else ''}."
    quantity = Decimal(quantity)
    if quantity < service.min_quantity:
        return f"أقل كمية لهذه الخدمة {service.min_quantity.normalize():f}{unit}."
    if service.max_quantity is not None and quantity > service.max_quantity:
        return f"أكبر كمية لهذه الخدمة {service.max_quantity.normalize():f}{unit}."
    return None


def apply_quantity(attrs, user, instance, *, doctor, service):
    """Price a booking of a service sold by quantity, in the serializer's
    validated data. Returns the message for a bad quantity, else None.

    * A service that takes a quantity: the total is the doctor's unit price
      (contract, else catalogue) × the quantity, and the unit price is kept
      with the booking so a later contract change never rewrites it. Anyone but
      management gets exactly that total; management may type another price
      (their existing right), and gets the computed one when they do not.
    * A service that does not: no quantity is kept.
    A booking edited without touching doctor, service or quantity keeps the
    figures it was made with.
    """
    if service is None or not service.requires_quantity:
        if instance is None or "service" in attrs or "quantity" in attrs:
            attrs["quantity"] = None
            attrs["unit_price"] = None
            attrs["quantity_is_estimate"] = False
        return None

    quantity = attrs["quantity"] if "quantity" in attrs else getattr(instance, "quantity", None)
    if quantity is None and service.doctor_sets_quantity:
        # Nothing asked for and the doctor will size it: booked at the smallest
        # quantity, as an estimate.
        quantity = service.min_quantity
        attrs["quantity"] = quantity
    problem = quantity_problem(service, quantity)
    if problem:
        return problem

    changed = instance is None or (
        getattr(instance, "doctor_id", None) != getattr(doctor, "pk", None)
        or getattr(instance, "service_id", None) != service.pk
        or Decimal(getattr(instance, "quantity", None) or 0) != Decimal(quantity)
    )
    if not changed:
        return None
    unit = price_for(doctor, service) or ZERO
    attrs["quantity"] = Decimal(quantity)
    attrs["unit_price"] = unit
    # Still the doctor's to confirm, if the service lets them.
    attrs["quantity_is_estimate"] = bool(service.doctor_sets_quantity)
    if not is_clinic_admin(user) or "price" not in attrs:
        attrs["price"] = quantity_total(unit, quantity)
    return None


class QuantityRefused(Exception):
    """The doctor's quantity cannot be recorded. The message is for the doctor."""


CHANGEABLE_BY_DOCTOR = ("waiting", "called", "entered")


def set_final_quantity(appointment, quantity):
    """The doctor fixes the real quantity of a service sold by quantity.

    The booking keeps the unit price it was made with (a contract that changed
    since does not touch it); the total becomes unit price × the doctor's
    quantity, a coupon's discount can never exceed it, and the booking stops
    being an estimate. Returns `(old_total, new_total)`. What was paid is not
    touched — the difference is for the front desk to collect (or return).
    """
    service = appointment.service
    if service is None or not (service.requires_quantity and service.doctor_sets_quantity):
        raise QuantityRefused("هذه الخدمة لا يحدد الطبيب كميتها.")
    if appointment.status not in CHANGEABLE_BY_DOCTOR:
        raise QuantityRefused("لا يمكن تحديد الكمية لحجز مغلق أو لم يؤكَّد بعد.")
    if quantity in (None, ""):
        raise QuantityRefused(quantity_problem(service, None))
    try:
        quantity = Decimal(str(quantity)).quantize(CENT)
    except Exception:  # noqa: BLE001 — anything that is not a number
        raise QuantityRefused("الكمية غير صالحة.")
    problem = quantity_problem(service, quantity)
    if problem:
        raise QuantityRefused(problem)

    unit = appointment.unit_price
    if unit is None:
        unit = price_for(appointment.doctor, service) or ZERO
    old_total = appointment.price
    appointment.quantity = quantity
    appointment.unit_price = unit
    appointment.price = quantity_total(unit, quantity)
    appointment.discount = min(appointment.discount or ZERO, appointment.price)
    appointment.quantity_is_estimate = False
    appointment.save(update_fields=["quantity", "unit_price", "price", "discount", "quantity_is_estimate"])
    return old_total, appointment.price
