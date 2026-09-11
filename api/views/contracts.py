"""Doctor contracts and doctor shares (billing.pricing, billing.commissions).

    /api/doctor-rates/               management writes; a doctor reads their own
    /api/doctor-rates/quote/         ?doctor=&service= → the price a booking gets
    /api/commissions/                a doctor's own shares; management's clinic
    /api/commissions/summary/        pending / settled totals for the same filter
    POST /api/commissions/settle/    {uuids: [...]} — management marks received
"""

from django.db.models import Q
from rest_framework import permissions
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from accounts.roles import (
    current_branch_id,
    is_clinic_admin,
    is_doctor,
    sees_all_branches,
)
from api.permissions import IsClinicMember
from api.serializers.billing import DoctorCommissionSerializer, DoctorServiceRateSerializer
from api.viewsets import ClinicViewSet, ReadOnlyClinicViewSet
from billing.commissions import settle, totals
from billing.models import DoctorCommission, DoctorServiceRate
from billing.pricing import price_for
from employees.models import Employee
from services.models import Service


class ContractsReadable(permissions.BasePermission):
    """Management reads and writes contracts; a doctor reads their own; nobody
    else sees what a doctor is paid."""

    message = "التعاقدات مقصورة على إدارة العيادة."

    def has_permission(self, request, view):
        if getattr(view, "action", None) == "quote":
            return True
        if request.method in permissions.SAFE_METHODS:
            return is_clinic_admin(request.user) or is_doctor(request.user)
        return is_clinic_admin(request.user)


class DoctorServiceRateViewSet(ClinicViewSet):
    queryset = DoctorServiceRate.objects.all()
    serializer_class = DoctorServiceRateSerializer
    permission_classes = [IsClinicMember, ContractsReadable]
    # A contract line has no clinic of its own; it follows its doctor, home
    # clinic or any the Owner linked them to. Scoped by hand below.
    branch_field = None
    ordering = ["doctor__name", "service__name"]

    def filter_tenant_queryset(self, queryset):
        user = self.request.user
        queryset = queryset.select_related("doctor", "service")
        if is_doctor(user):
            return queryset.filter(doctor_id=user.employee_id) if user.employee_id else queryset.none()
        if not sees_all_branches(user):
            branch_id = current_branch_id(user)
            queryset = queryset.filter(
                Q(doctor__branch_id=branch_id) | Q(doctor__extra_branches=branch_id)
            ).distinct()
        doctor = self.request.query_params.get("doctor")
        if doctor:
            queryset = queryset.filter(doctor__uuid=doctor)
        return queryset

    @action(detail=False, methods=["get"], url_path="quote")
    def quote(self, request):
        """The price a booking with this doctor and service gets — for the
        booking form to show before saving. The price only, never the share."""
        doctor = Employee.objects.filter(uuid=request.query_params.get("doctor")).first()
        service = Service.objects.filter(uuid=request.query_params.get("service")).first()
        return Response({"price": price_for(doctor, service) if service else None})


class DoctorCommissionViewSet(ReadOnlyClinicViewSet):
    queryset = DoctorCommission.objects.all()
    serializer_class = DoctorCommissionSerializer
    permission_classes = [IsClinicMember]
    http_method_names = ["get", "post", "head", "options"]
    ordering = ["-created_at"]

    def filter_tenant_queryset(self, queryset):
        user = self.request.user
        # A doctor is narrowed to their own by the branch/doctor scoping in
        # ClinicViewSet (accounts.roles); the front desk sees none at all.
        if not (is_clinic_admin(user) or is_doctor(user)):
            return queryset.none()
        queryset = queryset.select_related("doctor", "patient", "branch", "payment", "settled_by")
        params = self.request.query_params
        if params.get("status"):
            queryset = queryset.filter(status=params["status"])
        if params.get("doctor"):
            queryset = queryset.filter(doctor__uuid=params["doctor"])
        if params.get("from"):
            queryset = queryset.filter(created_at__date__gte=params["from"])
        if params.get("to"):
            queryset = queryset.filter(created_at__date__lte=params["to"])
        return queryset

    def create(self, request, *args, **kwargs):
        raise PermissionDenied("تُحتسب النسب تلقائياً من الدفعات.")

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        return Response(totals(self.filter_queryset(self.get_queryset()).order_by()))

    @action(detail=False, methods=["post"], url_path="settle")
    def settle(self, request):
        """Management hands the doctor their share and records it here."""
        if not is_clinic_admin(request.user):
            raise PermissionDenied("تسجيل استلام النسبة مقصور على إدارة العيادة.")
        uuids = request.data.get("uuids") or []
        count = settle(request.user, self.get_queryset().filter(uuid__in=uuids))
        return Response({"settled": count})
