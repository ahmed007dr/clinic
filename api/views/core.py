"""Branches, services and staff."""

from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

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
    search_fields = ["name", "serial_number", "national_id", "phone1", "phone2"]
    ordering = ["name"]

    def filter_tenant_queryset(self, queryset):
        queryset = queryset.select_related(
            "employee_type", "branch", "salary_type"
        ).prefetch_related("specializations", "extra_branches")
        params = self.request.query_params
        if params.get("employee_type"):
            queryset = queryset.filter(employee_type__uuid=params["employee_type"])
        if params.get("branch"):
            queryset = queryset.filter(branch__uuid=params["branch"])
        return queryset

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
    # By name or by phone: the desk knows a doctor by either.
    search_fields = ["name", "phone1", "phone2"]
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


    @action(detail=False, methods=["get"], url_path="offerings")
    def offerings(self, request):
        """What a booking form may offer once a doctor is chosen.

        `?doctor=<uuid>`: only the services the doctor is under contract for
        (an active contract line, an active service) with the price each will
        cost — the contract price, else the catalogue price — and only the
        doctor's own specialties. No `doctor`: the whole catalogue at its
        catalogue prices, for a booking not yet given to anyone.

        Prices only, never the doctor's share: the receptionist booking needs
        to tell the patient what they will pay, not what the doctor earns.
        """
        from billing.models import DoctorServiceRate

        doctor_uuid = request.query_params.get("doctor")
        if not doctor_uuid:
            services = Service.objects.filter(is_active=True).select_related("specialization")
            return Response({
                "contracted": False,
                "services": [_offer(service, service.base_price) for service in services.order_by("name")],
                "specializations": [
                    {"uuid": str(s.uuid), "name": s.name} for s in Specialization.objects.order_by("name")
                ],
            })

        # Through the same scoping as the picker: a doctor this user may not
        # book is a 404, not a price list.
        doctor = self.get_queryset().filter(uuid=doctor_uuid).first()
        if doctor is None:
            raise NotFound()
        rates = (
            DoctorServiceRate.objects.filter(doctor=doctor, is_active=True, service__is_active=True)
            .select_related("service", "service__specialization")
            .order_by("service__name")
        )
        return Response({
            "contracted": True,
            "services": [
                _offer(rate.service, rate.price if rate.price is not None else rate.service.base_price)
                for rate in rates
            ],
            "specializations": [
                {"uuid": str(s.uuid), "name": s.name} for s in doctor.specializations.order_by("name")
            ],
        })


def _offer(service, price):
    specialization = service.specialization
    return {
        "uuid": str(service.uuid),
        "name": service.name,
        "price": str(price),
        "specialization": str(specialization.uuid) if specialization else None,
    }
