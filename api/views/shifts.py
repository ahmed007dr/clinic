"""Cash shifts (billing.shifts holds every rule; this only speaks HTTP).

    GET  /api/shifts/current/          your open shift and its running summary
    POST /api/shifts/open/             {opening_balance, notes}
    POST /api/shifts/<uuid>/close/     your own, or anyone's if you manage shifts
    GET  /api/shifts/                  management: the clinic's shifts
    GET  /api/shifts/<uuid>/           management: one shift, its money, summary
    POST /api/shifts/<uuid>/reopen/    management only
"""

from decimal import Decimal, InvalidOperation

from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from api.permissions import IsClinicMember
from api.serializers.billing import ExpenseSerializer, PaymentSerializer
from api.viewsets import ReadOnlyClinicViewSet
from billing.models import CashShift
from billing.shifts import (
    ShiftError,
    can_close,
    close_shift,
    current_shift,
    manages_shifts,
    open_shift,
    reopen_shift,
    summarize,
    visible_shifts,
    works_in_shifts,
)


class CashShiftSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.username", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    closed_by_name = serializers.CharField(source="closed_by.username", read_only=True, default=None)
    reopened_by_name = serializers.CharField(source="reopened_by.username", read_only=True, default=None)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = CashShift
        fields = [
            "uuid", "user_name", "branch_name", "status", "status_label",
            "opening_balance", "opened_at", "closed_at", "closed_by_name",
            "reopened_at", "reopened_by_name", "closing_summary", "notes",
        ]
        read_only_fields = fields


def _refuse(error):
    raise ValidationError({"detail": str(error)})


class CashShiftViewSet(ReadOnlyClinicViewSet):
    queryset = CashShift.objects.all()
    serializer_class = CashShiftSerializer
    permission_classes = [IsClinicMember]
    # visible_shifts does the scoping: management's clinic, nobody else's.
    branch_field = None
    http_method_names = ["get", "post", "head", "options"]
    ordering = ["-opened_at"]

    def filter_tenant_queryset(self, queryset):
        queryset = visible_shifts(self.request.user, queryset).select_related(
            "user", "branch", "closed_by", "reopened_by"
        )
        params = self.request.query_params
        if params.get("status"):
            queryset = queryset.filter(status=params["status"])
        if params.get("from"):
            queryset = queryset.filter(opened_at__date__gte=params["from"])
        if params.get("to"):
            queryset = queryset.filter(opened_at__date__lte=params["to"])
        if params.get("branch"):
            queryset = queryset.filter(branch__uuid=params["branch"])
        return queryset

    def create(self, request, *args, **kwargs):
        raise PermissionDenied("افتح الوردية من /api/shifts/open/.")

    def payload(self, shift, *, full=False):
        data = CashShiftSerializer(shift).data
        data["summary"] = summarize(shift)
        if full:
            context = self.get_serializer_context()
            data["payments"] = PaymentSerializer(
                shift.payments.select_related("patient", "method", "branch", "appointment")
                .order_by("date"), many=True, context=context,
            ).data
            data["expenses"] = ExpenseSerializer(
                shift.expenses.select_related("branch", "category", "employee", "method")
                .order_by("id"), many=True, context=context,
            ).data
        return data

    def retrieve(self, request, *args, **kwargs):
        return Response(self.payload(self.get_object(), full=True))

    @action(detail=False, methods=["get"], url_path="current")
    def current(self, request):
        """Your own open shift — the only shift a receptionist ever reaches."""
        if not works_in_shifts(request.user):
            return Response({"works_in_shifts": False, "shift": None})
        shift = current_shift(request.user)
        return Response({
            "works_in_shifts": True,
            "shift": self.payload(shift, full=True) if shift else None,
        })

    @action(detail=False, methods=["post"], url_path="open")
    def open(self, request):
        try:
            balance = Decimal(str(request.data.get("opening_balance") or "0"))
        except InvalidOperation:
            raise ValidationError({"opening_balance": "أدخل مبلغاً صحيحاً."})
        try:
            shift = open_shift(request.user, balance, request.data.get("notes", ""))
        except ShiftError as error:
            _refuse(error)
        return Response(self.payload(shift, full=True), status=201)

    def shift_for_action(self, uuid):
        """The shift an action names: your own, or — for management — any in
        their clinic. A receptionist naming someone else's shift gets 404."""
        own = CashShift.objects.filter(uuid=uuid, user=self.request.user).first()
        if own is not None:
            return own
        return visible_shifts(self.request.user).filter(uuid=uuid).first()

    @action(detail=True, methods=["post"], url_path="close")
    def close(self, request, uuid=None):
        shift = self.shift_for_action(uuid)
        if shift is None or not can_close(request.user, shift):
            from django.http import Http404

            raise Http404
        try:
            shift = close_shift(request.user, shift, request.data.get("notes"))
        except ShiftError as error:
            _refuse(error)
        # The person who ran it loses sight of it the moment it closes; they
        # get the frozen summary once, as the receipt of what they handed over.
        if manages_shifts(request.user):
            return Response(self.payload(shift, full=True))
        return Response({"closed": True, "closing_summary": shift.closing_summary})

    @action(detail=True, methods=["post"], url_path="reopen")
    def reopen(self, request, uuid=None):
        shift = self.get_object()  # visible_shifts: management only
        try:
            shift = reopen_shift(request.user, shift)
        except ShiftError as error:
            _refuse(error)
        return Response(self.payload(shift, full=True))
