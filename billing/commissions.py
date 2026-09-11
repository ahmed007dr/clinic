"""The doctor's share of what is actually paid — accrued, corrected, settled.

The group owner's rules (2026-09-11):

* A share is a percentage of the amount **actually paid**, not of the price.
  It accrues the moment a payment is recorded, for the booking's doctor, at the
  percentage their contract gives that service (billing.pricing.percent_for).
  No percentage agreed means nothing accrues — never a guessed one.
* The service, its original price and the percentage are copied in, so a later
  contract change leaves earned shares as they were.
* Management marks shares received; until then they are pending. A doctor sees
  their own and nothing else (the doctor filter in accounts.roles).
* A correction to a payment (an Admin's) re-computes its share while it is
  still pending; a share already handed over is never rewritten.

Driven by signals on Payment, so every door that records money — the API, the
older screens — accrues the same way.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.utils import timezone

from .models import DoctorCommission, Payment
from .pricing import percent_for, price_for

CENT = Decimal("0.01")


def share(amount, percent):
    return (Decimal(amount) * Decimal(percent) / Decimal(100)).quantize(CENT, rounding=ROUND_HALF_UP)


def accrue(payment):
    """Create or refresh the pending share for `payment`. Returns it, or None
    when there is no doctor or no agreed percentage."""
    appointment = payment.appointment
    doctor = getattr(appointment, "doctor", None)
    existing = DoctorCommission.all_objects.filter(payment=payment).first()
    if existing is not None and existing.status == DoctorCommission.Status.SETTLED:
        return existing
    if payment.voided_at is not None:
        # Cancelled money earns nobody a share (billing.voiding).
        if existing is not None:
            existing.delete()
        return None
    percent = percent_for(doctor, appointment.service) if doctor else None
    if percent is None:
        if existing is not None:
            existing.delete()
        return None
    service = appointment.service
    fields = {
        "tenant_id": payment.tenant_id,
        "doctor": doctor,
        "branch_id": payment.branch_id or appointment.branch_id,
        "appointment": appointment,
        "patient_id": payment.patient_id,
        "service": service,
        "description": getattr(service, "name", "") or "كشف",
        "original_price": appointment.price or price_for(doctor, service) or 0,
        "paid_amount": payment.amount,
        "percent": percent,
        "amount": share(payment.amount, percent),
    }
    if existing is None:
        return DoctorCommission.all_objects.create(payment=payment, **fields)
    for name, value in fields.items():
        setattr(existing, name, value)
    existing.save()
    return existing


def settle(actor, commissions):
    """Mark pending shares as handed over to the doctor. Returns the count."""
    return commissions.filter(status=DoctorCommission.Status.PENDING).update(
        status=DoctorCommission.Status.SETTLED, settled_at=timezone.now(), settled_by=actor,
    )


def totals(commissions):
    """Pending and settled sums for a queryset of shares."""
    from django.db.models import Sum

    rows = dict(
        commissions.values_list("status").annotate(total=Sum("amount")).values_list("status", "total")
    )
    pending = Decimal(rows.get(DoctorCommission.Status.PENDING) or 0).quantize(CENT)
    settled = Decimal(rows.get(DoctorCommission.Status.SETTLED) or 0).quantize(CENT)
    return {"pending": str(pending), "settled": str(settled), "total": str(pending + settled)}


@receiver(post_save, sender=Payment)
def accrue_on_payment(sender, instance, created, **kwargs):
    commission = accrue(instance)
    if created and commission is not None:
        from .notify import email_doctor_payment

        transaction.on_commit(lambda: email_doctor_payment(commission.pk))


@receiver(pre_delete, sender=Payment)
def drop_pending_share(sender, instance, **kwargs):
    # The payment is going, and with it the money a pending share was a slice
    # of. A settled one stays: it was handed over (payment is SET_NULL on it).
    # pre_delete, because by post_delete the SET_NULL has already cut the link.
    DoctorCommission.all_objects.filter(
        payment_id=instance.pk, status=DoctorCommission.Status.PENDING
    ).delete()
