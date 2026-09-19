"""Cash shifts — opening, recording under, closing, reopening, summarising.

The rules (the group owner's, 2026-09-11):

* A receptionist, clinic Admin or the group Owner opens their own shift. It
  starts from zero (the group owner's rule, 2026-09-18: no opening balance, no
  "expected" balance) — the drawer is whatever the shift itself took in and
  paid out. Every payment or expense they record goes
  into it; with no open shift they cannot record money at all — nobody is
  exempt (the group owner's rule, 2026-09-18: money recorded outside a shift
  is a drawer that cannot be reconciled, and the Owner was the gap).
* The closing report is per payment method: what came in, what went out, the
  net — which is what the drawer is checked against, at any moment.
* Closing: by the person themselves at the end of their day, or by an
  Admin/Owner. After that the person cannot see it (billing.access).
* Reopening: Admin or Owner only.

Views call these functions; none of the rules above live in a view.
"""

from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from accounts.roles import ADMIN, OWNER, RECEPTION, is_clinic_admin, role_name, sees_all_branches

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
    """Who records money inside a shift: the front desk, clinic Admins and the
    Owner. Doctors record no clinic money at all."""
    return role_name(user) in {RECEPTION, ADMIN, OWNER}


def manages_shifts(user):
    """Who reviews, closes anyone's, and reopens shifts."""
    return is_clinic_admin(user)


def current_shift(user):
    """The user's open shift, or None."""
    return CashShift.objects.filter(user=user, status=CashShift.Status.OPEN).first()


def shift_for_recording(user):
    """The shift a new payment or expense by `user` goes into.

    None only for a role that records no money through the clinic screens.
    For everyone who works in shifts an open shift is required — money
    recorded with nowhere to go is exactly the drawer that cannot be
    reconciled.
    """
    if not works_in_shifts(user):
        return None
    shift = current_shift(user)
    if shift is None:
        raise ShiftError("افتح ورديتك أولاً: لا يمكن تسجيل مبالغ بدون وردية مفتوحة.")
    return shift


def open_shift(user, notes="", branch=None):
    """Open `user`'s shift on their own clinic. It starts at zero. The Owner sees every clinic, so
    they may name the one they are working at (`branch`, a Branch); nobody
    else can open a shift anywhere but their own clinic."""
    if not works_in_shifts(user):
        raise ShiftError("الورديات للاستقبال وإدارة العيادة فقط.")
    branch_id = user.branch_id
    if branch is not None and sees_all_branches(user):
        branch_id = branch.pk
    if not branch_id:
        raise ShiftError(
            "اختر الفرع الذي ستعمل عليه." if sees_all_branches(user) else "حسابك غير مرتبط بفرع."
        )
    try:
        with transaction.atomic():
            return CashShift.objects.create(
                tenant=user.tenant, user=user, branch_id=branch_id,
                opening_balance=ZERO, notes=notes or "",
            )
    except IntegrityError:
        # The partial unique constraint: a second open shift for this user.
        raise ShiftError("لديك وردية مفتوحة بالفعل.")


ONLINE_SHIFT_NAME = "الدفع الإلكتروني"


def shift_owner_name(shift):
    """Whose shift it is, for screens and print: the person, or — for the
    online shift, which belongs to nobody — its name."""
    if shift is None:
        return None
    if shift.kind == CashShift.Kind.ONLINE or shift.user_id is None:
        return ONLINE_SHIFT_NAME
    from accounts.roles import display_name

    return display_name(shift.user)


def online_shift(tenant, branch_id):
    """The clinic's open online shift, opened now if there is none.

    Every confirmed online payment is recorded inside a shift, like all money
    (the group owner's rule, 2026-09-18 and 2026-09-19): a payment a gateway
    confirmed is not "paid" until it sits in a shift. No cashier has to be at
    the desk for that — the online payments of a clinic are gathered in one
    shift of their own, which management closes and reviews (and after which
    the next payment opens a fresh one). At most one is open per clinic
    (`one_open_online_shift_per_branch`); two payments arriving together
    cannot open two.
    """
    if not branch_id:
        raise ShiftError("لا يمكن تسجيل الدفع الإلكتروني: الحجز غير مرتبط بفرع.")
    shift = CashShift.objects.filter(
        branch_id=branch_id, kind=CashShift.Kind.ONLINE, status=CashShift.Status.OPEN
    ).first()
    if shift is not None:
        return shift
    try:
        with transaction.atomic():
            return CashShift.objects.create(
                tenant=tenant, branch_id=branch_id, kind=CashShift.Kind.ONLINE, user=None,
                opening_balance=ZERO, notes="وردية الدفع الإلكتروني — تُفتح تلقائياً وتُغلق بمراجعة الإدارة.",
            )
    except IntegrityError:
        # Another payment opened it a moment ago.
        return CashShift.objects.get(
            branch_id=branch_id, kind=CashShift.Kind.ONLINE, status=CashShift.Status.OPEN
        )


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


#: How long after closing the person who ran a shift may still print it — the
#: handover receipt. Longer than that it is management's to review and print
#: (billing.access: a closed shift is no longer the cashier's to see).
HANDOVER_PRINT_WINDOW = timedelta(minutes=30)


def printable_shift(user, uuid):
    """The shift `uuid` if `user` may print its report, else None.

    Management: any shift they can review. Anyone else who works in shifts:
    their own — while it is open, or in the handover window after they closed
    it (so they can print what they hand over).
    """
    shift = (
        CashShift.objects.select_related("user", "branch", "closed_by", "reopened_by")
        .filter(uuid=uuid).first()
    )
    if shift is None:
        return None
    if visible_shifts(user, CashShift.objects.filter(pk=shift.pk)).exists():
        return shift
    if shift.user_id != user.pk or not works_in_shifts(user):
        return None
    if shift.is_open:
        return shift
    recently = shift.closed_at and timezone.now() - shift.closed_at <= HANDOVER_PRINT_WINDOW
    return shift if recently and shift.closed_by_id == user.pk else None


def summarize(shift):
    """Per payment method: revenue in, expenses out, net. Plus the totals.
    Amounts are strings, so the frozen copy in `closing_summary` is exact JSON."""
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
        "revenue": _money(revenue),
        "expenses": _money(spent),
        "net": _money(revenue - spent),
        "by_method": by_method,
    }


def shift_bookings(shift):
    """The bookings made in this shift: by its person, from when it opened
    (until it closed) — each with what has been paid and what is still owed,
    so the drawer can be counted against them at any moment. Newest first."""
    from appointments.models import Appointment

    if shift.kind == CashShift.Kind.ONLINE:
        # No person made these bookings: the shift's bookings are the ones paid in it.
        return (
            Appointment.objects.filter(payments__shift=shift).distinct()
            .select_related("patient", "doctor", "service", "branch", "specialization")
            .prefetch_related("visits", "payments")
            .order_by("-created_at", "-id")
        )
    queryset = Appointment.objects.filter(created_by_id=shift.user_id, created_at__gte=shift.opened_at)
    if shift.closed_at:
        queryset = queryset.filter(created_at__lte=shift.closed_at)
    return (
        queryset.select_related("patient", "doctor", "service", "branch", "specialization")
        .prefetch_related("visits", "payments")
        .order_by("-created_at", "-id")
    )


def _counts(queryset):
    from django.db.models import Count

    for entry in queryset.values("method_id").annotate(n=Count("id")):
        yield entry["method_id"], entry["n"]
