"""Branches, services and staff."""

from rest_framework.filters import OrderingFilter, SearchFilter

from api.permissions import IsClinicAdmin, IsClinicMember, ReadOnlyForNonAdmin, ReadOnlyForNonOwner
from api.serializers.core import (
    BranchSerializer,
    DoctorBriefSerializer,
    EmployeeSerializer,
    EmployeeTypeSerializer,
    SalaryTypeSerializer,
    ServiceSerializer,
    SpecializationSerializer,
)
from api.viewsets import ClinicViewSet, ReadOnlyClinicViewSet
from rest_framework.exceptions import PermissionDenied
from subscriptions.entitlements import LimitReached, check_limit
from subscriptions.usage import doctor_count, limit_message
from tenants.context import get_current_tenant
from branches.models import Branch
from employees.models import Employee, EmployeeType, SalaryType, Specialization
from services.models import Service


class BranchViewSet(ClinicViewSet):
    """Every clinic member can list branches — a booking form needs them.

    Only an Admin may create or change one, and `branch_field = None` because a
    branch is not inside a branch: scoping the list would leave a receptionist
    unable to see the name of the place they work.
    """

    queryset = Branch.objects.all()
    serializer_class = BranchSerializer
    # Adding or reshaping clinics is the group owner's decision.
    permission_classes = [ReadOnlyForNonOwner]
    plan_limit = "max_branches"
    branch_field = None
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["name", "code", "phone"]
    ordering = ["name"]


class EmployeeTypeViewSet(ClinicViewSet):
    queryset = EmployeeType.objects.all()
    serializer_class = EmployeeTypeSerializer
    permission_classes = [ReadOnlyForNonAdmin]
    branch_field = None
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["name"]
    ordering = ["name"]


class SpecializationViewSet(ClinicViewSet):
    queryset = Specialization.objects.all()
    serializer_class = SpecializationSerializer
    permission_classes = [ReadOnlyForNonAdmin]
    branch_field = None
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["name"]
    ordering = ["name"]


class SalaryTypeViewSet(ClinicViewSet):
    queryset = SalaryType.objects.all()
    serializer_class = SalaryTypeSerializer
    permission_classes = [IsClinicAdmin]
    branch_field = None
    ordering = ["name"]


class ServiceViewSet(ClinicViewSet):
    queryset = Service.objects.all()
    serializer_class = ServiceSerializer
    permission_classes = [ReadOnlyForNonAdmin]
    branch_field = None
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["name", "description"]
    ordering = ["name"]

    def filter_tenant_queryset(self, queryset):
        return queryset.select_related("specialization")


class EmployeeViewSet(ClinicViewSet):
    """Staff records, including salary — Admin only, for that reason.

    The doctor picker that every booking form needs is a separate, narrower
    endpoint (`DoctorViewSet`) so reception can book without being handed the
    payroll.
    """

    queryset = Employee.objects.all()
    serializer_class = EmployeeSerializer
    permission_classes = [IsClinicAdmin]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["name", "serial_number", "national_id", "phone1"]
    ordering = ["name"]

    def filter_tenant_queryset(self, queryset):
        return queryset.select_related(
            "employee_type", "branch", "salary_type"
        ).prefetch_related("specializations")

    # The same two limits the server-rendered employee screens enforce
    # (WIRE-003). Counted clinic-wide, never through the caller's branch view.
    @staticmethod
    def _is_doctor(employee_type):
        return getattr(employee_type, "name", None) == "Doctor"

    def _refuse(self, limit, count):
        try:
            check_limit(get_current_tenant(), limit, count)
        except LimitReached as reached:
            raise PermissionDenied(limit_message(reached))

    def perform_create(self, serializer):
        self._refuse("max_staff", Employee.objects.count())
        if self._is_doctor(serializer.validated_data.get("employee_type")):
            self._refuse("max_doctors", doctor_count())
        super().perform_create(serializer)

    def perform_update(self, serializer):
        before = serializer.instance.employee_type
        after = serializer.validated_data.get("employee_type", before)
        if self._is_doctor(after) and not self._is_doctor(before):
            self._refuse("max_doctors", doctor_count())
        super().perform_update(serializer)


class DoctorViewSet(ReadOnlyClinicViewSet):
    """Doctors, for pickers. Name and branch only."""

    queryset = Employee.objects.all()
    serializer_class = DoctorBriefSerializer
    permission_classes = [IsClinicMember]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["name"]
    ordering = ["name"]

    def filter_tenant_queryset(self, queryset):
        return queryset.select_related("branch").prefetch_related("specializations").filter(
            employee_type__name="Doctor"
        )
