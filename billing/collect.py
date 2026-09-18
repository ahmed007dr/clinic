"""Money against a booking: what is owed, what is paid, and who may go in.

The group owner's rules (2026-09-18) — none of them lives in a view:

* A payment belongs to a booking. It is taken with the booking, or later for
  the rest, and either way goes into the recorder's open cash shift
  (billing.shifts). A payment cannot exceed what the booking still owes.
* A patient goes in to the doctor only once the booking is paid in full —
  net of any discount coupon — unless management gave them a coupon.
* A coupon (billing.DiscountCoupon) is issued in the patient's name by an
  Admin or the Owner for a service or a specialty, and is spent once, on a
  booking. Nobody else discounts anything.

Views and serializers call these functions.
"""

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from appointments.models import Appointment
from tenants.models import SerialCounter

from .models import DiscountCoupon, Payment
from .shifts import shift_for_recording

ZERO = Decimal("0")
CENT = Decimal("0.01")


class PaymentRefused(Exception):
    """A payment rule refused the action. The message is for the user."""


class PaymentRequired(Exception):
    """The booking is not paid in full, so the patient may not go in yet."""


def money(value):
    return Decimal(value or 0).quantize(CENT)


def amount_paid(appointment):
    """What has actually been paid on the booking (cancelled payments left out)."""
    total = (
        Payment.all_objects.filter(appointment=appointment, voided_at__isnull=True)
        .aggregate(total=Sum("amount"))["total"]
    )
    return money(total)


def amount_due(appointment, price=None):
    """What the booking still owes: net price less what has been paid, never
    below zero. `price` lets a caller ask about a price not yet saved."""
    net = appointment.net_price if price is None else max(Decimal(price) - (appointment.discount or 0), ZERO)
    return money(max(net - amount_paid(appointment), ZERO))


def new_receipt_number(tenant_id):
    """The next receipt number, issued by the system — typing one by hand was
    how two receipts came to share a number."""
    return "R-" + SerialCounter.next_serial(tenant_id, "receipt", timezone.now().date())


def record_payment(user, appointment, amount, method=None, notes=""):
    """Take `amount` against `appointment` into `user`'s open shift.

    Refused with `PaymentRefused` (or `ShiftError` when there is no open shift)
    rather than half-done: nothing is written unless all of it is.
    """
    amount = Decimal(amount)
    if amount <= 0:
        raise PaymentRefused("المبلغ يجب أن يكون أكبر من صفر.")
    shift = shift_for_recording(user)
    if shift is None:
        raise PaymentRefused("لا يمكنك تسجيل مبالغ.")
    with transaction.atomic():
        # Locked, so two desks collecting the same balance at once cannot both
        # pass the "not more than is owed" check below.
        locked = Appointment.all_objects.select_for_update().get(pk=appointment.pk)
        due = amount_due(locked)
        if amount > due:
            raise PaymentRefused(f"المبلغ أكبر من المتبقي على الحجز ({due}).")
        return Payment.all_objects.create(
            tenant_id=locked.tenant_id,
            appointment=locked,
            patient_id=locked.patient_id,
            method=method,
            receipt_number=new_receipt_number(locked.tenant_id),
            amount=amount,
            branch=shift.branch,
            shift=shift,
            created_by=user,
            notes=notes or None,
        )


def require_paid(due):
    """Raise `PaymentRequired` if `due` — what is still owed — is more than nothing."""
    if due > 0:
        raise PaymentRequired(
            f"لا يمكن دخول المريض قبل سداد المبلغ كاملاً — المتبقي {money(due)} ج.م. "
            "حصّل المتبقي، أو اطلب من الإدارة كوبون خصم باسم المريض."
        )


def check_can_enter(appointment, price=None):
    """Raise `PaymentRequired` unless the booking is paid in full."""
    require_paid(amount_due(appointment, price))


# ------------------------------------------------------------------- coupons


def coupon_problem(coupon, patient, service, specialization, today=None):
    """Why `coupon` cannot be used on this booking, or None if it can."""
    if coupon.patient_id != getattr(patient, "pk", None):
        return "هذا الكوبون ليس باسم هذا المريض."
    status = coupon.status
    if status == "used":
        return "هذا الكوبون استُخدم من قبل."
    if status == "voided":
        return "هذا الكوبون ملغى."
    if status == "expired":
        return "انتهت صلاحية هذا الكوبون."
    if not coupon.applies_to(service, specialization):
        return "هذا الكوبون لا ينطبق على الخدمة أو التخصص المختار."
    return None


def available_coupons(patient):
    """The patient's coupons that can still be used (any service or specialty)."""
    today = timezone.now().date()
    live = DiscountCoupon.all_objects.filter(
        patient=patient, voided_at__isnull=True, used_at__isnull=True
    )
    return [c for c in live.select_related("service", "specialization")
            if not c.expires_on or c.expires_on >= today]


def spend_coupon(coupon):
    """Mark the coupon used, atomically: a second booking racing for the same
    coupon finds it already spent."""
    updated = DiscountCoupon.all_objects.filter(
        pk=coupon.pk, used_at__isnull=True, voided_at__isnull=True
    ).update(used_at=timezone.now())
    if not updated:
        raise PaymentRefused("هذا الكوبون استُخدم من قبل.")
