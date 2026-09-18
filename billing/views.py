"""Server-rendered pages the React app links to: the payment and expense receipts,
the shift report, and the PDF / Excel export of the payments search. Recording
and listing money is the React app and the API (billing.collect, billing.shifts)."""

from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render

from accounts.roles import is_clinic_admin, scope_queryset_to_user
from utils.utils import export_excel, export_pdf

from .models import DoctorCommission, Expense, Payment


def is_admin(user):
    return is_clinic_admin(user)


@login_required
def payment_list_export(request):
    """PDF / Excel of the payments the search screen is showing (period, clinic,
    patient, name or receipt) — never the whole ledger unasked. A logged-in user
    who may not export gets a 403, not a bounce through the login page."""
    from django.core.exceptions import PermissionDenied

    if not is_admin(request.user):
        raise PermissionDenied('التصدير مقصور على إدارة العيادة.')
    params = request.GET
    payments = scope_queryset_to_user(Payment.objects.select_related('patient', 'method'), request.user)
    if params.get('from'):
        payments = payments.filter(date__date__gte=params['from'])
    if params.get('to'):
        payments = payments.filter(date__date__lte=params['to'])
    if params.get('branch'):
        payments = payments.filter(branch__uuid=params['branch'])
    if params.get('patient'):
        payments = payments.filter(patient__uuid=params['patient'])
    for word in (params.get('search') or '').split():
        payments = payments.filter(
            Q(receipt_number__icontains=word) | Q(patient__name__icontains=word)
            | Q(appointment__serial_number__icontains=word)
        )
    payments = payments.order_by('-date')
    export_format = params.get('export')
    data = [
        [p.receipt_number, p.patient.name, str(p.amount), p.method.name if p.method else 'غير محدد', p.date.strftime('%Y-%m-%d')]
        for p in payments
    ]
    headers = ['رقم الإيصال', 'المريض', 'المبلغ', 'طريقة الدفع', 'التاريخ']
    title = f'قائمة الدفعات - فرع {request.user.branch.name if request.user.branch else "الكل"}'
    filename = f'payment_list_{datetime.now().strftime("%Y%m%d")}'
    if export_format == 'pdf':
        return export_pdf(data, headers, title, filename)
    elif export_format == 'excel':
        return export_excel(data, headers, title, filename)
    return HttpResponseBadRequest('صيغة التصدير غير معروفة: استخدم export=pdf أو export=excel.')


@login_required
def payment_print(request, uuid):
    """The receipt handed over when a payment is recorded (the group owner's
    rule, 2026-09-12) — reprintable any time, for whoever may still see this
    payment at all (billing.access: management always, reception only while
    their shift holding it is still open).
    """
    from accounts.roles import display_name
    from branches.printing import letterhead, receipt_layout
    from .access import visible_payments

    payment = get_object_or_404(
        visible_payments(request.user, Payment.objects.select_related(
            "patient", "method", "branch", "appointment", "appointment__doctor", "created_by",
        )),
        uuid=uuid,
    )
    return render(request, "billing/payment_print.html", {
        "letterhead": letterhead(payment.branch, request),
        "layout": receipt_layout(payment.branch),
        "payment": payment,
        "recorded_by": display_name(payment.created_by) if payment.created_by else "—",
    })


@login_required
def expense_print(request, uuid):
    """The receipt for a recorded expense — same rule as `payment_print`."""
    from accounts.roles import display_name
    from branches.printing import letterhead, receipt_layout
    from .access import visible_expenses

    expense = get_object_or_404(
        visible_expenses(request.user, Expense.objects.select_related(
            "branch", "category", "employee", "method", "created_by",
        )),
        uuid=uuid,
    )
    return render(request, "billing/expense_print.html", {
        "letterhead": letterhead(expense.branch, request),
        "layout": receipt_layout(expense.branch),
        "expense": expense,
        "recorded_by": display_name(expense.created_by) if expense.created_by else "—",
    })


@login_required
def shift_print(request, uuid):
    """The shift report: whose drawer, opened and closed when, the takings and
    payouts per payment method, and every payment and expense with its
    details. For reception (their own shift, at handover), the clinic Admin
    and the Owner — `billing.shifts.printable_shift` decides who."""
    from accounts.roles import display_name
    from branches.printing import letterhead, receipt_layout
    from .shifts import printable_shift, summarize

    shift = printable_shift(request.user, uuid)
    if shift is None:
        raise Http404

    # Cancelled money is not in the drawer; the report lists only what counts.
    payments = (
        Payment.all_objects.filter(shift=shift, voided_at__isnull=True)
        .select_related("patient", "method", "appointment", "appointment__service", "appointment__doctor")
        .order_by("date")
    )
    expenses = (
        Expense.all_objects.filter(shift=shift, voided_at__isnull=True)
        .select_related("category", "employee", "method")
        .order_by("id")
    )
    summary = summarize(shift)
    closing = shift.closing_summary or None
    return render(request, "billing/shift_print.html", {
        "letterhead": letterhead(shift.branch, request),
        "layout": receipt_layout(shift.branch),
        "shift": shift,
        "cashier": display_name(shift.user),
        "closed_by": display_name(shift.closed_by) if shift.closed_by else None,
        "printed_by": display_name(request.user),
        "summary": summary,
        "changed_since_closing": bool(closing) and closing.get("net") != summary["net"],
        "payments": payments,
        "expenses": expenses,
    })


@login_required
def commission_report_print(request):
    """The doctors' shares for a period, printed for signature: what each
    doctor earned (or was handed) service by service, with a line for the
    doctor to sign as received and one for the admin who handed it over.

    Takes the same filters as the screen (`billing.commissions.narrow`), so
    what is printed is what was on screen. Management prints for their clinic;
    a doctor prints their own only (`scope_queryset_to_user`); the front desk
    has no business with the doctors' money.
    """
    from django.core.exceptions import PermissionDenied

    from accounts.roles import display_name, is_doctor
    from branches.printing import letterhead, receipt_layout
    from .commissions import narrow, totals

    user = request.user
    if not (is_clinic_admin(user) or is_doctor(user)):
        raise PermissionDenied('تقرير نسب الأطباء مقصور على الإدارة والأطباء.')

    params = request.GET
    shares = narrow(
        scope_queryset_to_user(
            DoctorCommission.objects.select_related("doctor", "patient", "branch"), user
        ),
        params,
    ).order_by("doctor__name", "doctor_id", "created_at")

    # One block per doctor, each with its own subtotal and signature line: the
    # sheet is handed to each of them to sign for what is theirs.
    blocks = []
    for share in shares:
        if not blocks or blocks[-1]["doctor"].pk != share.doctor_id:
            blocks.append({"doctor": share.doctor, "rows": []})
        blocks[-1]["rows"].append(share)
    for block in blocks:
        block["totals"] = totals(shares.filter(doctor_id=block["doctor"].pk))

    status = params.get("status")
    branch = getattr(user, "branch", None) if getattr(user, "branch_id", None) else None
    return render(request, "billing/commission_report_print.html", {
        "letterhead": letterhead(branch, request),
        "layout": receipt_layout(branch),
        "blocks": blocks,
        "grand": totals(shares),
        "count": sum(len(block["rows"]) for block in blocks),
        "status_label": {"pending": "المعلّقة", "settled": "المستلمة"}.get(status, "المعلّقة والمستلمة"),
        "date_from": params.get("from") or None,
        "date_to": params.get("to") or None,
        "printed_by": display_name(user),
    })
