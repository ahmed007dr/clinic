"""Branches, services and staff."""

from rest_framework.filters import OrderingFilter, SearchFilter

from api.permissions import IsClinicAdmin, IsClinicMember, ReadOnlyForNonAdmin, ReadOnlyForNonOwner
from accounts.roles import is_clinic_admin, sees_all_branches
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

    def filter_tenant_queryset(self, queryset):
        # A stopped clinic is the Owner's to see (and restart); for everyone
        # else it is not a place anything can be booked into.
        if not sees_all_branches(self.request.user):
            queryset = queryset.filter(is_active=True)
        return queryset


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
        queryset = queryset.select_related("specialization")
        # A stopped service is out of every picker; management still lists it
        # (to restart it) and can ask for either kind with ?active=1/0.
        active = self.request.query_params.get("active")
        if not is_clinic_admin(self.request.user):
            return queryset.filter(is_active=True)
        if active in ("1", "0"):
            queryset = queryset.filter(is_active=active == "1")
        return queryset


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
        ).prefetch_related("specializations", "extra_branches")

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

    # Scoped by hand below: a doctor the Owner linked to several clinics must
    # be bookable in each of them, not only in their home branch.
    branch_field = None

    def filter_tenant_queryset(self, queryset):
        from django.db.models import Q

        from accounts.roles import current_branch_id, sees_all_branches

        queryset = queryset.select_related("branch").prefetch_related("specializations").filter(
            employee_type__name="Doctor"
        # A doctor whose account management has stopped is not bookable.
        ).exclude(user_account__is_active=False)
        user = self.request.user
        if sees_all_branches(user):
            return queryset
        branch_id = current_branch_id(user)
        if not branch_id:
            return queryset.none()
        return queryset.filter(Q(branch_id=branch_id) | Q(extra_branches=branch_id)).distinct()
