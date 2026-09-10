"""Appointments and the waiting queue."""

from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from api.permissions import IsClinicMember
from api.serializers.appointments import AppointmentSerializer
from api.viewsets import ClinicViewSet
from appointments.models import Appointment


class AppointmentViewSet(ClinicViewSet):
    queryset = Appointment.objects.all()
    serializer_class = AppointmentSerializer
    permission_classes = [IsClinicMember]
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
        )
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
        appointment.status = value
        appointment.save(update_fields=["status"])
        return Response(self.get_serializer(appointment).data)
