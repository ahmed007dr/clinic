"""Appointments and the waiting queue."""

from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from accounts.roles import is_front_desk
from api.permissions import DeleteRequiresAdmin, IsClinicMember
from api.serializers.appointments import AppointmentSerializer
from api.viewsets import ClinicViewSet
from appointments.models import Appointment


class AppointmentViewSet(ClinicViewSet):
    queryset = Appointment.objects.all()
    serializer_class = AppointmentSerializer
    permission_classes = [IsClinicMember, DeleteRequiresAdmin]
    created_by_field = "created_by"
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = [
        "serial_number", "patient__name", "patient__phone1", "doctor__name",
    ]
    ordering_fields = ["scheduled_date", "created_at", "serial_number"]
    ordering = ["-scheduled_date"]

    def filter_tenant_queryset(self, queryset):
        queryset = queryset.select_related(
            "patient", "doctor", "service", "branch", "specialization"
        ).prefetch_related("visits", "payments")
        params = self.request.query_params

        status = params.get("status")
        if status:
            queryset = queryset.filter(status=status)

        # A branch filter is only meaningful for someone who can see more than
        # one; for everybody else the queryset is already narrowed and this
        # would be a no-op at best and a way to probe at worst.
        branch = params.get("branch")
        if branch:
            queryset = queryset.filter(branch__uuid=branch)

        doctor = params.get("doctor")
        if doctor:
            queryset = queryset.filter(doctor__uuid=doctor)

        date_from = params.get("from")
        if date_from:
            queryset = queryset.filter(scheduled_date__date__gte=date_from)
        date_to = params.get("to")
        if date_to:
            queryset = queryset.filter(scheduled_date__date__lte=date_to)

        # The front desk's view of what is coming: bookings after today, and
        # which of them are already paid for — to check them in on the day.
        if params.get("upcoming") == "1":
            queryset = queryset.filter(scheduled_date__date__gt=timezone.now().date())
        paid = params.get("paid")
        if paid in ("1", "0") and is_front_desk(self.request.user):
            from django.db.models import Exists, OuterRef

            from billing.models import Payment

            has_payment = Exists(Payment.objects.filter(appointment=OuterRef("pk")))
            queryset = queryset.filter(has_payment if paid == "1" else ~has_payment)

        return queryset

    @action(detail=False, methods=["get"], url_path="today")
    def today(self, request):
        """The day's list, which is what the front desk actually opens."""
        queryset = self.filter_queryset(self.get_queryset()).filter(
            scheduled_date__date=timezone.now().date()
        )
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page or queryset, many=True)
        return (
            self.get_paginated_response(serializer.data)
            if page is not None
            else Response(serializer.data)
        )

    @action(detail=False, methods=["get"], url_path="waiting")
    def waiting(self, request):
        """The queue: who is here now, in arrival order.

        Ordered ascending rather than by newest-first — a queue is read from
        the front.
        """
        queryset = (
            self.filter_queryset(self.get_queryset())
            .filter(status__in=["waiting", "entered", "called"])
            .filter(scheduled_date__date=timezone.now().date())
            .order_by("scheduled_date")
        )
        return Response(self.get_serializer(queryset, many=True).data)

    @action(detail=True, methods=["post"], url_path="status")
    def set_status(self, request, uuid=None):
        """Move one booking through the queue.

        A dedicated endpoint rather than a PATCH so that advancing the queue
        cannot carry an edit of the price or the patient alongside it.
        """
        appointment = self.get_object()
        value = request.data.get("status")
        allowed = {choice for choice, _ in Appointment.STATUS_CHOICES}
        if value not in allowed:
            return Response(
                {"status": [f"قيمة غير صالحة. المسموح: {'، '.join(sorted(allowed))}"]},
                status=400,
            )
        if value == "entered" and appointment.doctor_id is None:
            # Sending a patient in opens their visit under the booking's
            # doctor (medical/checkin.py); with no doctor it would be a visit
            # no doctor can see.
            return Response(
                {"status": ["حدد الطبيب في الحجز قبل تسجيل دخول المريض."]}, status=400
            )
        appointment.status = value
        appointment.save(update_fields=["status"])
        return Response(self.get_serializer(appointment).data)

    @action(detail=True, methods=["post"], url_path="follow-up")
    def follow_up(self, request, uuid=None):
        """`{date}` — the follow-up date on this booking's visit.

        The one part of a visit the front desk sets (the doctor can too, on
        the visit itself): booking the next appointment is their job, and it
        must not require opening the medical record to do it.
        """
        from django.utils.dateparse import parse_date

        from medical.models import Visit

        appointment = self.get_object()
        visit = Visit.all_objects.filter(appointment=appointment).first()
        if visit is None:
            return Response({"detail": "لم يدخل المريض للطبيب بعد في هذا الحجز."}, status=400)
        raw = request.data.get("date")
        date = parse_date(raw) if raw else None
        if raw and date is None:
            return Response({"date": ["تاريخ غير صالح."]}, status=400)
        visit.follow_up_date = date
        visit.save(update_fields=["follow_up_date", "updated_at"])
        # Re-read: the booking's visits were prefetched before the change.
        return Response(self.get_serializer(self.get_object()).data)

    @action(detail=True, methods=["get"], url_path="prescriptions")
    def prescriptions(self, request, uuid=None):
        """This booking's prescriptions, as print links — no medicines, no
        diagnosis. The front desk prints them for the doctor to sign; the
        contents are on the printed sheet, not in this list."""
        from django.urls import reverse

        from medical.models import Prescription

        appointment = self.get_object()
        rows = (
            Prescription.all_objects.filter(visit__appointment=appointment)
            .select_related("doctor")
            .order_by("issued_at")
        )
        return Response([
            {
                "uuid": str(row.uuid),
                "serial_number": row.serial_number,
                "issued_at": row.issued_at,
                "doctor_name": getattr(row.doctor, "name", None),
                "print_url": reverse("medical:prescription_print", args=[row.uuid]),
            }
            for row in rows
        ])

