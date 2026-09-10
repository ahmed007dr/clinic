"""The group owner's dashboard — every clinic of the group, in one request.

The group is the tenant, so none of this crosses a tenant boundary: the
connection is bound to the owner's own group by `TenantMiddleware` and
row-level security, exactly as for every other request. Another group's
clinics are not filtered out here; they are simply not visible to this query.

How double counting is avoided — the thing an aggregate dashboard most easily
gets wrong:

* Each figure is computed from its own table (payments, expenses,
  appointments, patients, attendance) with one grouping per query. Revenue is
  never computed across a join to expenses or appointments, so no row can be
  multiplied by another table's rows.
* Revenue is attributed through the payment's own foreign keys (its clinic;
  its appointment's doctor), each of which points at exactly one row.
* "Returning patients" uses EXISTS subqueries, not a join, so a patient with
  five appointments is one patient.
* The group total is computed directly, not by adding the clinic rows — so a
  payment with no clinic still counts in the total, and is visible as the
  difference.
"""

from datetime import date, timedelta

from django.db.models import (
    Count, DecimalField, Exists, F, OuterRef, Q, Subquery, Sum, Value,
)
from django.db.models.functions import Coalesce, Greatest
from django.utils.dateparse import parse_date
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.roles import scope_queryset_to_user
from api.permissions import IsGroupOwner
from appointments.models import Appointment
from billing.models import Expense, Payment
from branches.models import Branch
from employees.models import Attendance, Employee
from medical.models import PatientIntake
from patients.models import Patient

MONEY = DecimalField(max_digits=14, decimal_places=2)
ZERO = Value(0, output_field=MONEY)
MAX_RANGE_DAYS = 366
NOT_HAPPENING = ("cancelled", "no_show")


def _range(params):
    today = date.today()
    start = parse_date(params.get("from") or "") or today.replace(day=1)
    end = parse_date(params.get("to") or "") or today
    if params.get("from") and parse_date(params["from"]) is None:
        raise ValidationError({"from": "تاريخ غير صالح."})
    if params.get("to") and parse_date(params["to"]) is None:
        raise ValidationError({"to": "تاريخ غير صالح."})
    if start > end:
        raise ValidationError({"from": "بداية الفترة بعد نهايتها."})
    if (end - start).days > MAX_RANGE_DAYS:
        raise ValidationError({"to": "أقصى فترة سنة واحدة."})
    return start, end


def _by(queryset, key, **aggregates):
    return {row[key]: row for row in queryset.values(key).annotate(**aggregates)}


class OwnerOverviewView(APIView):
    """`GET /api/owner/overview/?from=YYYY-MM-DD&to=YYYY-MM-DD&branch=<uuid>`"""

    permission_classes = [IsGroupOwner]

    def get(self, request):
        user = request.user
        start, end = _range(request.query_params)
        today = date.today()

        # Every clinic of the group. The tenant binding already limits this to
        # the owner's own group; IsGroupOwner limits it to the owner.
        branches = Branch.objects.order_by("name")
        selected = None
        if request.query_params.get("branch"):
            # Tenant-scoped lookup: another group's clinic is simply not found.
            selected = Branch.objects.filter(uuid=request.query_params["branch"]).first()
            if selected is None:
                raise NotFound("العيادة غير موجودة.")

        def in_scope(queryset, field="branch"):
            queryset = scope_queryset_to_user(queryset, user, field)
            return queryset.filter(**{f"{field}_id": selected.pk}) if selected else queryset

        payments = in_scope(Payment.objects.filter(date__date__gte=start, date__date__lte=end))
        expenses = in_scope(Expense.objects.filter(date__gte=start, date__lte=end))
        appointments = in_scope(Appointment.objects.filter(
            scheduled_date__date__gte=start, scheduled_date__date__lte=end))
        patients = in_scope(Patient.objects.filter(needs_review=False))
        intakes = in_scope(PatientIntake.objects.filter(created_at__date__gte=start, created_at__date__lte=end))
        attendance = in_scope(Attendance.objects.filter(date__gte=start, date__lte=end))
        doctors = in_scope(Employee.objects.filter(employee_type__name="Doctor")).select_related("branch")

        revenue = payments.aggregate(total=Coalesce(Sum("amount"), ZERO), count=Count("id"))
        spend = expenses.aggregate(total=Coalesce(Sum("amount"), ZERO), count=Count("id"))

        # ---- billed vs collected, per appointment in the period ---------------
        billable = appointments.exclude(status__in=NOT_HAPPENING)
        paid = (Payment.objects.filter(appointment=OuterRef("pk")).values("appointment")
                .annotate(t=Sum("amount")).values("t"))
        billing = billable.annotate(
            paid=Coalesce(Subquery(paid, output_field=MONEY), ZERO)
        ).annotate(
            due=Greatest(F("price") - F("paid"), ZERO)
        ).aggregate(
            billed=Coalesce(Sum("price"), ZERO),
            collected=Coalesce(Sum("paid"), ZERO),
            outstanding=Coalesce(Sum("due"), ZERO),
        )

        # ---- per clinic: one grouped query per measure -------------------------
        rev_by_branch = _by(payments, "branch", total=Sum("amount"))
        exp_by_branch = _by(expenses, "branch", total=Sum("amount"))
        appt_by_branch = _by(
            appointments, "branch", total=Count("id"),
            completed=Count("id", filter=Q(status="completed")),
            cancelled=Count("id", filter=Q(status="cancelled")),
            no_show=Count("id", filter=Q(status="no_show")),
        )
        new_by_branch = _by(patients.filter(created_at__date__gte=start, created_at__date__lte=end),
                            "branch", total=Count("id"))
        patients_by_branch = _by(patients, "branch", total=Count("id"))
        doctors_by_branch = _by(doctors, "branch", total=Count("id"))
        att_by_branch = _by(
            attendance, "branch",
            present=Count("id", filter=Q(status="present")),
            late=Count("id", filter=Q(status="late")),
            absent=Count("id", filter=Q(status="absent")),
            leave=Count("id", filter=Q(status="leave")),
        )

        def attendance_rate(row):
            worked = (row or {}).get("present", 0) + (row or {}).get("late", 0)
            expected = worked + (row or {}).get("absent", 0)
            return round(worked * 100 / expected, 1) if expected else None

        clinic_rows = []
        for branch in ([selected] if selected else branches):
            rev = (rev_by_branch.get(branch.pk) or {}).get("total") or 0
            exp = (exp_by_branch.get(branch.pk) or {}).get("total") or 0
            appt = appt_by_branch.get(branch.pk) or {}
            att = att_by_branch.get(branch.pk)
            clinic_rows.append({
                "uuid": str(branch.uuid),
                "name": branch.name,
                "revenue": rev,
                "expenses": exp,
                "net": rev - exp,
                "appointments": appt.get("total", 0),
                "completed": appt.get("completed", 0),
                "cancelled": appt.get("cancelled", 0),
                "no_show": appt.get("no_show", 0),
                "patients": (patients_by_branch.get(branch.pk) or {}).get("total", 0),
                "new_patients": (new_by_branch.get(branch.pk) or {}).get("total", 0),
                "doctors": (doctors_by_branch.get(branch.pk) or {}).get("total", 0),
                "attendance_rate": attendance_rate(att),
                "absences": (att or {}).get("absent", 0),
                "late": (att or {}).get("late", 0),
            })

        # ---- revenue by doctor and by specialty --------------------------------
        revenue_by_doctor = [
            {"uuid": str(r["appointment__doctor__uuid"]) if r["appointment__doctor__uuid"] else None,
             "name": r["appointment__doctor__name"], "total": r["total"], "count": r["count"]}
            for r in payments.values("appointment__doctor__uuid", "appointment__doctor__name")
            .annotate(total=Sum("amount"), count=Count("id")).order_by("-total")[:20]
        ]
        revenue_by_specialty = [
            {"name": r["specialty"], "total": r["total"]}
            for r in payments.annotate(
                specialty=Coalesce("appointment__specialization__name",
                                   "appointment__service__specialization__name")
            ).values("specialty").annotate(total=Sum("amount")).order_by("-total")
        ]

        # ---- trends -------------------------------------------------------------
        rev_days = {r["day"]: r["total"] for r in payments.values(day=F("date__date")).annotate(total=Sum("amount"))}
        exp_days = {r["date"]: r["total"] for r in expenses.values("date").annotate(total=Sum("amount"))}
        span = (end - start).days
        series = [
            {"date": d, "revenue": rev_days.get(d, 0) or 0, "expenses": exp_days.get(d, 0) or 0}
            for d in (start + timedelta(days=i) for i in range(span + 1))
        ]
        expense_by_category = [
            {"name": r["category__name"], "total": r["total"]}
            for r in expenses.values("category__name").annotate(total=Sum("amount")).order_by("-total")
        ]

        # ---- appointments --------------------------------------------------------
        all_appointments = in_scope(Appointment.objects.all())
        todays = all_appointments.filter(scheduled_date__date=today)
        appointment_stats = {
            "total": appointments.count(),
            "by_status": {r["status"]: r["n"] for r in appointments.values("status").annotate(n=Count("id"))},
            "today": todays.count(),
            "today_by_status": {r["status"]: r["n"] for r in todays.values("status").annotate(n=Count("id"))},
            "upcoming_7_days": all_appointments.filter(
                scheduled_date__date__gt=today, scheduled_date__date__lte=today + timedelta(days=7)
            ).exclude(status__in=NOT_HAPPENING).count(),
        }

        # ---- patients -------------------------------------------------------------
        in_period = all_appointments.filter(
            patient=OuterRef("pk"), scheduled_date__date__gte=start, scheduled_date__date__lte=end)
        before = all_appointments.filter(patient=OuterRef("pk"), scheduled_date__date__lt=start)
        patient_stats = {
            "total": patients.count(),
            "new": patients.filter(created_at__date__gte=start, created_at__date__lte=end).count(),
            "returning": patients.filter(Exists(in_period), Exists(before)).count(),
            "seen_in_period": patients.filter(Exists(in_period)).count(),
            "pending_review": in_scope(Patient.objects.filter(needs_review=True)).count(),
            "by_referral_source": {
                (r["referral_source"] or "unknown"): r["n"]
                for r in patients.filter(created_at__date__gte=start, created_at__date__lte=end)
                .values("referral_source").annotate(n=Count("id"))
            },
        }
        case_stats = {
            "by_case_type": {r["case_type"]: r["n"] for r in intakes.values("case_type").annotate(n=Count("id"))},
            "by_specialty": [
                {"name": r["specialization__name"], "n": r["n"]}
                for r in intakes.values("specialization__name").annotate(n=Count("id")).order_by("-n")
            ],
        }

        # ---- doctors: workload and attendance, two grouped queries ------------
        workload = _by(appointments, "doctor", total=Count("id"),
                       completed=Count("id", filter=Q(status="completed")),
                       no_show=Count("id", filter=Q(status="no_show")))
        doctor_attendance = _by(
            attendance.filter(employee__in=doctors), "employee",
            present=Count("id", filter=Q(status="present")),
            late=Count("id", filter=Q(status="late")),
            absent=Count("id", filter=Q(status="absent")),
            leave=Count("id", filter=Q(status="leave")),
        )
        doctor_rows = [
            {
                "uuid": str(d.uuid), "name": d.name,
                "branch": d.branch.name if d.branch else None,
                "appointments": (workload.get(d.pk) or {}).get("total", 0),
                "completed": (workload.get(d.pk) or {}).get("completed", 0),
                "no_show": (workload.get(d.pk) or {}).get("no_show", 0),
                "present": (doctor_attendance.get(d.pk) or {}).get("present", 0),
                "late": (doctor_attendance.get(d.pk) or {}).get("late", 0),
                "absent": (doctor_attendance.get(d.pk) or {}).get("absent", 0),
                "leave": (doctor_attendance.get(d.pk) or {}).get("leave", 0),
            }
            for d in doctors.order_by("branch__name", "name")[:200]
        ]
        staff_attendance = attendance.aggregate(
            present=Count("id", filter=Q(status="present")),
            late=Count("id", filter=Q(status="late")),
            absent=Count("id", filter=Q(status="absent")),
            leave=Count("id", filter=Q(status="leave")),
        )

        return Response({
            "filters": {"from": start, "to": end, "branch": str(selected.uuid) if selected else None},
            "branches": [{"uuid": str(b.uuid), "name": b.name} for b in branches],
            "finance": {
                "revenue": revenue["total"], "payments": revenue["count"],
                "expenses": spend["total"], "expense_entries": spend["count"],
                "net": revenue["total"] - spend["total"],
                "billed": billing["billed"], "collected": billing["collected"],
                "outstanding": billing["outstanding"],
            },
            "clinics": clinic_rows,
            "revenue_by_doctor": revenue_by_doctor,
            "revenue_by_specialty": revenue_by_specialty,
            "expense_by_category": expense_by_category,
            "series": series,
            "appointments": appointment_stats,
            "patients": patient_stats,
            "cases": case_stats,
            "doctors": doctor_rows,
            "attendance": {**staff_attendance, "rate": attendance_rate(staff_attendance)},
        })
