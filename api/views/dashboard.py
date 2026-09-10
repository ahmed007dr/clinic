"""The landing screen's numbers, in one request.

Assembled server-side because a dashboard built from eight list endpoints is
eight round trips that each transfer rows the screen then throws away in order
to count them.

Every figure is derived from `scope_queryset_to_user`, so a receptionist sees
their branch's day and an Admin sees the clinic's — the same rule as every
list, applied to aggregates.
"""

from datetime import timedelta

from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.permissions import (
    IsClinicMember,
    can_view_clinical,
    is_clinic_admin,
    scope_queryset_to_user,
)
from appointments.models import Appointment
from billing.models import Expense, Payment
from medical.models import LabResult, TreatmentPlan, Visit
from patients.models import Patient


class DashboardView(APIView):
    permission_classes = [IsClinicMember]

    def get(self, request):
        user = request.user
        today = timezone.now().date()
        month_start = today.replace(day=1)

        patients = scope_queryset_to_user(Patient.objects.all(), user)
        appointments = scope_queryset_to_user(Appointment.objects.all(), user)
        payments = scope_queryset_to_user(Payment.objects.all(), user)

        today_appointments = appointments.filter(scheduled_date__date=today)
        month_payments = payments.filter(date__date__gte=month_start)

        data = {
            "today": today,
            "patients": {
                "total": patients.count(),
                "new_this_month": patients.filter(
                    created_at__date__gte=month_start
                ).count(),
            },
            "appointments": {
                "today": today_appointments.count(),
                "waiting": today_appointments.filter(
                    status__in=["waiting", "entered", "called"]
                ).count(),
                "upcoming": appointments.filter(
                    scheduled_date__date__gt=today,
                    scheduled_date__date__lte=today + timedelta(days=7),
                ).count(),
            },
            "revenue": {
                "today": payments.filter(date__date=today).aggregate(
                    total=Sum("amount")
                )["total"]
                or 0,
                "month": month_payments.aggregate(total=Sum("amount"))["total"] or 0,
            },
        }

        # Money out is an Admin figure. Reception records payments; the clinic's
        # margin is not theirs to see.
        if is_clinic_admin(user):
            expenses = scope_queryset_to_user(Expense.objects.all(), user)
            month_expenses = (
                expenses.filter(date__gte=month_start).aggregate(
                    total=Sum("amount")
                )["total"]
                or 0
            )
            data["expenses"] = {"month": month_expenses}
            data["revenue"]["net_month"] = data["revenue"]["month"] - month_expenses

        if can_view_clinical(user):
            visits = scope_queryset_to_user(Visit.objects.all(), user)
            labs = scope_queryset_to_user(LabResult.objects.all(), user)
            plans = scope_queryset_to_user(TreatmentPlan.objects.all(), user)
            data["clinical"] = {
                "visits_today": visits.filter(visit_date__date=today).count(),
                # The number that should make someone act: an abnormal result
                # nobody has confirmed reading.
                "unacknowledged_labs": labs.filter(
                    acknowledged_at__isnull=True
                ).exclude(flag=LabResult.Flag.NORMAL).count(),
                "active_plans": plans.filter(
                    status=TreatmentPlan.Status.ACTIVE
                ).count(),
            }

        # A fortnight of daily takings, for the chart.
        series = (
            payments.filter(date__date__gte=today - timedelta(days=13))
            .values("date__date")
            .annotate(total=Sum("amount"), count=Count("id"))
            .order_by("date__date")
        )
        by_day = {row["date__date"]: row for row in series}
        data["revenue_series"] = [
            {
                "date": day,
                "total": by_day.get(day, {}).get("total") or 0,
                "count": by_day.get(day, {}).get("count") or 0,
            }
            for day in (today - timedelta(days=offset) for offset in range(13, -1, -1))
        ]

        return Response(data)
