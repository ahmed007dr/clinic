"""Branches, services and staff — the reference data everything else points at."""

from rest_framework import serializers

from api.relations import TenantScopedRelatedField
from branches.models import Branch
from employees.models import Employee, EmployeeType, SalaryType, Specialization
from services.models import Service

from .common import ClinicSerializer


class BranchSerializer(ClinicSerializer):
    class Meta:
        model = Branch
        fields = [
            "uuid", "name", "code", "address", "phone", "email", "footer_text",
        ]


class EmployeeTypeSerializer(ClinicSerializer):
    class Meta:
        model = EmployeeType
        fields = ["uuid", "name", "description"]


class SpecializationSerializer(ClinicSerializer):
    class Meta:
        model = Specialization
        fields = ["uuid", "name", "description"]


class SalaryTypeSerializer(ClinicSerializer):
    class Meta:
        model = SalaryType
        fields = ["uuid", "name"]


class ServiceSerializer(ClinicSerializer):
    specialization = TenantScopedRelatedField(
        model=Specialization, required=False, allow_null=True
    )
    specialization_name = serializers.CharField(
        source="specialization.name", read_only=True, default=None
    )

    class Meta:
        model = Service
        fields = [
            "uuid", "name", "description",
            "specialization", "specialization_name", "base_price",
        ]


class EmployeeSerializer(ClinicSerializer):
    employee_type = TenantScopedRelatedField(
        model=EmployeeType, required=False, allow_null=True
    )
    branch = TenantScopedRelatedField(model=Branch)
    salary_type = TenantScopedRelatedField(
        model=SalaryType, required=False, allow_null=True
    )
    specializations = TenantScopedRelatedField(
        model=Specialization, many=True, required=False
    )

    employee_type_name = serializers.CharField(
        source="employee_type.name", read_only=True, default=None
    )
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    specialization_names = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = [
            "uuid", "serial_number", "name",
            "employee_type", "employee_type_name",
            "branch", "branch_name",
            "national_id", "phone1", "phone2", "email",
            "hire_date", "salary_type", "salary_value",
            "specializations", "specialization_names",
        ]

    def get_specialization_names(self, employee):
        return [s.name for s in employee.specializations.all()]


class DoctorBriefSerializer(ClinicSerializer):
    """Doctors only, for the pickers on appointment and clinical forms.

    A separate serializer rather than a filtered `EmployeeSerializer` because
    the pickers must not leak salary figures to whoever is booking a visit.
    """

    branch_name = serializers.CharField(source="branch.name", read_only=True)

    class Meta:
        model = Employee
        fields = ["uuid", "name", "branch", "branch_name"]
        read_only_fields = fields
