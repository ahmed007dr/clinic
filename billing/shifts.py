"""Cash shifts — opening, recording under, closing, reopening, summarising.

The rules (the group owner's, 2026-09-11):

* A receptionist or clinic Admin opens their own shift, with the cash already
  in the drawer. Every payment or expense they record goes into it; with no
  open shift they cannot record money at all. The Owner records outside
  shifts.
* The closing report is per payment method: what came in, what went out, the
  net — plus the opening balance, so the drawer can be checked against it.
* Closing: by the person themselves at the end of their day, or by an
  Admin/Owner. After that the person cannot see it (billing.access).
* Reopening: Admin or Owner only.

Views call these functions; none of the rules above live in a view.
"""

from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from accounts.roles import ADMIN, RECEPTION, is_clinic_admin, role_name, sees_all_branches

from .models import CashShift, Expense, Payment

ZERO = Decimal("0")
CENT = Decimal("0.01")


def _money(value):
    """Two places, always — SQLite's SUM drops them, PostgreSQL keeps them,
    and a frozen summary must read the same on both."""
    return str(Decimal(value or 0).quantize(CENT))


class ShiftError(Exception):
    """A shift rule refused the action. The message is for the user."""


def works_in_shifts(user):
    """Who records money inside a shift: the front desk and clinic Admins."""
    return role_name(user) in {RECEPTION, ADMIN}


def manages_shifts(user):
    """Who reviews, closes anyone's, and reopens shifts."""
    return is_clinic_admin(user)


def current_shift(user):
    """The user's open shift, or None."""
    return CashShift.objects.filter(user=user, status=CashShift.Status.OPEN).first()


def shift_for_recording(user):
    """The shift a new payment or expense by `user` goes into.

    None for the Owner (records outside shifts). For everyone who works in
    shifts, an open shift is required — money recorded with nowhere to go is
    exactly the drawer that cannot be reconciled.
    """
    if not works_in_shifts(user):
        return None
    shift = current_shift(user)
    if shift is None:
        raise ShiftError("افتح ورديتك أولاً: لا يمكن تسجيل مبالغ بدون وردية مفتوحة.")
    return shift


def open_shift(user, opening_balance=ZERO, notes=""):
    if not works_in_shifts(user):
        raise ShiftError("الورديات للاستقبال وإدارة العيادة فقط.")
    if not user.branch_id:
        raise ShiftError("حسابك غير مرتبط بفرع.")
    if opening_balance is None or Decimal(opening_balance) < 0:
        raise ShiftError("الرصيد الافتتاحي لا يمكن أن يكون سالباً.")
    try:
        with transaction.atomic():
            return CashShift.objects.create(
                tenant=user.tenant, user=user, branch_id=user.branch_id,
                opening_balance=opening_balance, notes=notes or "",
            )
    except IntegrityError:
        # The partial unique constraint: a second open shift for this user.
        raise ShiftError("لديك وردية مفتوحة بالفعل.")


def can_close(actor, shift):
    return shift.user_id == actor.pk or manages_shifts(actor)


def close_shift(actor, shift, notes=None):
    if not shift.is_open:
        raise ShiftError("الوردية مغلقة بالفعل.")
    if not can_close(actor, shift):
        raise ShiftError("لا يمكنك إغلاق وردية موظف آخر.")
    shift.status = CashShift.Status.CLOSED
    shift.closed_at = timezone.now()
    shift.closed_by = actor
    shift.closing_summary = summarize(shift)
    if notes:
        shift.notes = f"{shift.notes}\n{notes}".strip()
    shift.save(update_fields=["status", "closed_at", "closed_by", "closing_summary", "notes"])
    return shift


def reopen_shift(actor, shift):
    if not manages_shifts(actor):
        raise ShiftError("إعادة فتح الوردية مقصورة على إدارة العيادة.")
    if shift.is_open:
        raise ShiftError("الوردية مفتوحة بالفعل.")
    shift.status = CashShift.Status.OPEN
    shift.reopened_at = timezone.now()
    shift.reopened_by = actor
    try:
        with transaction.atomic():
            shift.save(update_fields=["status", "reopened_at", "reopened_by"])
    except IntegrityError:
        raise ShiftError("لدى الموظف وردية أخرى مفتوحة الآن؛ يجب إغلاقها أولاً.")
    return shift


def visible_shifts(user, queryset=None):
    """Management sees the shifts of their clinic (the Owner, every clinic);
    everyone else sees none — their own open shift is reached through
    `current_shift`, never through the list."""
    queryset = CashShift.objects.all() if queryset is None else queryset
    if not manages_shifts(user):
        return queryset.none()
    if sees_all_branches(user):
        return queryset
    return queryset.filter(branch_id=user.branch_id) if user.branch_id else queryset.none()


def summarize(shift):
    """Per payment method: revenue in, expenses out, net. Plus the totals and
    the balance expected at the end (opening balance + net). Amounts are
    strings, so the frozen copy in `closing_summary` is exact JSON."""
    # Cancelled money is not in the drawer (billing.voiding).
    payments = Payment.all_objects.filter(shift=shift, voided_at__isnull=True)
    expenses = Expense.all_objects.filter(shift=shift, voided_at__isnull=True)

    rows = {}

    def row(method_id, name):
        return rows.setdefault(
            method_id, {"method": name or "غير محدد", "revenue": ZERO, "expenses": ZERO,
                        "payments_count": 0, "expenses_count": 0},
        )

    for entry in payments.values("method_id", "method__name").annotate(total=Sum("amount")):
        target = row(entry["method_id"], entry["method__name"])
        target["revenue"] = entry["total"] or ZERO
    for entry in expenses.values("method_id", "method__name").annotate(total=Sum("amount")):
        target = row(entry["method_id"], entry["method__name"])
        target["expenses"] = entry["total"] or ZERO
    for method_id, count in _counts(payments):
        rows[method_id]["payments_count"] = count
    for method_id, count in _counts(expenses):
        rows[method_id]["expenses_count"] = count

    by_method = []
    for data in sorted(rows.values(), key=lambda r: r["method"]):
        by_method.append({
            **data,
            "net": _money(data["revenue"] - data["expenses"]),
            "revenue": _money(data["revenue"]),
            "expenses": _money(data["expenses"]),
        })

    revenue = sum((Decimal(r["revenue"]) for r in by_method), ZERO)
    spent = sum((Decimal(r["expenses"]) for r in by_method), ZERO)
    return {
        "opening_balance": _money(shift.opening_balance),
        "revenue": _money(revenue),
        "expenses": _money(spent),
        "net": _money(revenue - spent),
        "expected_balance": _money(Decimal(shift.opening_balance) + revenue - spent),
        "by_method": by_method,
    }


def _counts(queryset):
    from django.db.models import Count

    for entry in queryset.values("method_id").annotate(n=Count("id")):
        yield entry["method_id"], entry["n"]
