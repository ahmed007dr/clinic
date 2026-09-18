"""A person's own report, emailed to their own address.

The group owner's rule (2026-09-12): doctors and staff can have their sheets
and reports sent to their email. Whose? Only ever the signed-in person's own,
to their own address — never an address typed in, so the endpoint cannot be
used to send clinic data anywhere else.

What each role gets is what its own screens show, built from the same scoping
helpers (`scope_queryset_to_user`, `visible_payments`, `visible_expenses`,
`billing.commissions.totals`), so an email can never say more than the screen:

* a doctor — their bookings (الكشوفات) and their share of what was paid;
* the front desk — the clinic's bookings, and the takings of their open shift;
* an Admin / the Owner — bookings, takings and expenses of their clinic
  (every clinic, for the Owner).
"""

from decimal import Decimal

from django.db.models import Count, Sum

from accounts.roles import is_clinic_admin, is_doctor, scope_queryset_to_user
from appointments.models import Appointment
from billing.access import visible_expenses, visible_payments
from billing.commissions import narrow, totals
from billing.models import DoctorCommission, Expense, Payment

ROW_CAP = 200


def _money(value):
    return f"{Decimal(value or 0):,.2f}"


def _capped(rows):
    rows = list(rows)
    return rows[:ROW_CAP], len(rows) > ROW_CAP


def recipient(user):
    employee = getattr(user, "employee", None)
    return (getattr(employee, "email", "") or user.email or "").strip()


def build(user, start, end):
    """(title, sections). A section is {heading, headers, rows, note}."""
    sections = []
    appointments = scope_queryset_to_user(
        Appointment.objects.select_related("patient", "doctor", "service"), user
    ).filter(scheduled_date__date__gte=start, scheduled_date__date__lte=end).order_by("scheduled_date")

    if is_doctor(user):
        rows, more = _capped(appointments)
        sections.append({
            "heading": "الكشوفات",
            "headers": ["الموعد", "المريض", "الخدمة", "الحالة"],
            "rows": [
                [f"{a.scheduled_date:%Y-%m-%d %H:%M}", a.patient.name,
                 getattr(a.service, "name", None) or "كشف", a.get_status_display()]
                for a in rows
            ],
            "note": f"عُرض أول {ROW_CAP} فقط." if more else "",
        })
        shares = narrow(
            scope_queryset_to_user(DoctorCommission.objects.select_related("patient"), user),
            {"from": start, "to": end},
        )
        summary = totals(shares.order_by())
        rows, more = _capped(shares.order_by("created_at"))
        sections.append({
            "heading": "نصيبك من الدفعات",
            "headers": ["التاريخ", "المريض", "الخدمة", "المدفوع", "النسبة", "نصيبك", "الحالة"],
            "rows": [
                [f"{c.created_at:%Y-%m-%d}", getattr(c.patient, "name", "—"), c.description,
                 _money(c.paid_amount), f"{c.percent}%", _money(c.amount), c.get_status_display()]
                for c in rows
            ],
            "note": f"معلّق: {_money(summary['pending'])} · مستلم: {_money(summary['settled'])}"
                    f" · الإجمالي: {_money(summary['total'])}",
        })
        return "تقريرك", sections

    labels = dict(Appointment.STATUS_CHOICES)
    by_status = appointments.order_by().values_list("status").annotate(n=Count("id"))
    sections.append({
        "heading": "الحجوزات",
        "headers": ["الحالة", "العدد"],
        "rows": [[labels.get(status, status), n] for status, n in by_status],
        "note": f"الإجمالي: {appointments.count()}",
    })

    payments = visible_payments(user, Payment.objects.all()).filter(
        date__date__gte=start, date__date__lte=end
    )
    by_method = payments.order_by().values_list("method__name").annotate(total=Sum("amount"), n=Count("id"))
    grand = payments.aggregate(total=Sum("amount"))["total"] or 0
    sections.append({
        "heading": "المقبوضات" if is_clinic_admin(user) else "مقبوضات ورديتك المفتوحة",
        "headers": ["طريقة الدفع", "المبلغ", "عدد الإيصالات"],
        "rows": [[name or "—", _money(total), n] for name, total, n in by_method],
        "note": f"الإجمالي: {_money(grand)}",
    })

    if is_clinic_admin(user):
        expenses = visible_expenses(user, Expense.objects.all()).filter(date__gte=start, date__lte=end)
        spent = expenses.aggregate(total=Sum("amount"))["total"] or 0
        by_category = expenses.order_by().values_list("category__name").annotate(total=Sum("amount"))
        sections.append({
            "heading": "المصروفات",
            "headers": ["البند", "المبلغ"],
            "rows": [[name or "غير محدد", _money(total)] for name, total in by_category],
            "note": f"الإجمالي: {_money(spent)} · الصافي: {_money(Decimal(grand) - Decimal(spent))}",
        })
    return "تقرير الفترة", sections
