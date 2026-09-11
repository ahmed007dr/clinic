"""Cancelling recorded money — with a reason, by management, on the record.

The group owner's rule (2026-09-11): a clinic Admin or the Owner can cancel a
payment or an expense that should not stand. Cancelled is not deleted: the row
stays, with who cancelled it, when and why, and simply stops counting — the
default manager (billing.models.LiveTenantManager) leaves it out of every
total, report, list and shift. A doctor's pending share of a cancelled payment
goes with it (billing.commissions); one already handed over stays on record.
"""

from django.utils import timezone

from accounts.roles import is_clinic_admin


class VoidError(Exception):
    """The message is for the user."""


def void(actor, record, reason):
    if not is_clinic_admin(actor):
        raise VoidError("إلغاء الإيراد أو المصروف مقصور على إدارة العيادة.")
    reason = (reason or "").strip()
    if not reason:
        raise VoidError("اكتب سبب الإلغاء.")
    if record.voided_at is not None:
        raise VoidError("ملغى بالفعل.")
    record.voided_at = timezone.now()
    record.voided_by = actor
    record.void_reason = reason[:300]
    # save() rather than update(): a payment's save is what lets its doctor's
    # pending share follow it out (billing.commissions).
    record.save(update_fields=["voided_at", "voided_by", "void_reason"])
    return record
