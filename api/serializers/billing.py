"""Payments in, expenses out."""

from rest_framework import serializers

from api.relations import TenantScopedRelatedField
from appointments.models import Appointment
from billing.models import Expense, ExpenseCategory, Payment, PaymentMethod
from branches.models import Branch
from employees.models import Employee
from patients.models import Patient

from .common import ClinicSerializer


class PaymentMethodSerializer(ClinicSerializer):
    class Meta:
        model = PaymentMethod
        fields = ["uuid", "name", "description"]


class ExpenseCategorySerializer(ClinicSerializer):
    class Meta:
        model = ExpenseCategory
        fields = ["uuid", "name", "description"]


class PaymentSerializer(ClinicSerializer):
    appointment = TenantScopedRelatedField(
        model=Appointment, branch_field="branch"
    )
    patient = TenantScopedRelatedField(model=Patient, branch_field="branch")
    method = TenantScopedRelatedField(
        model=PaymentMethod, required=False, allow_null=True
    )
    branch = TenantScopedRelatedField(model=Branch, required=False, allow_null=True)

    patient_name = serializers.CharField(source="patient.name", read_only=True)
    method_name = serializers.CharField(
        source="method.name", read_only=True, default=None
    )
    branch_name = serializers.CharField(
        source="branch.name", read_only=True, default=None
    )
    appointment_serial = serializers.CharField(
        source="appointment.serial_number", read_only=True
    )

    class Meta:
        model = Payment
        fields = [
            "uuid", "receipt_number", "amount",
            "appointment", "appointment_serial",
            "patient", "patient_name",
            "method", "method_name",
            "branch", "branch_name",
            "date", "notes",
        ]
        read_only_fields = ["date"]

    def validate(self, attrs):
        """The payment must belong to the appointment's patient.

        Nothing in the schema ties the two together, so without this a receipt
        can be filed against one patient for another patient's visit — which
        corrupts both the patient's financial history and the clinic's revenue
        by doctor.
        """
        appointment = attrs.get("appointment") or getattr(
            self.instance, "appointment", None
        )
        patient = attrs.get("patient") or getattr(self.instance, "patient", None)
        if appointment and patient and appointment.patient_id != patient.pk:
            raise serializers.ValidationError(
                {"patient": "المريض لا يطابق المريض المرتبط بالموعد."}
            )
        return attrs


class ExpenseSerializer(ClinicSerializer):
    branch = TenantScopedRelatedField(model=Branch)
    category = TenantScopedRelatedField(
        model=ExpenseCategory, required=False, allow_null=True
    )
    employee = TenantScopedRelatedField(
        model=Employee, required=False, allow_null=True, branch_field="branch"
    )

    branch_name = serializers.CharField(source="branch.name", read_only=True)
    category_name = serializers.CharField(
        source="category.name", read_only=True, default=None
    )
    employee_name = serializers.CharField(
        source="employee.name", read_only=True, default=None
    )

    class Meta:
        model = Expense
        fields = [
            "uuid", "amount", "date",
            "branch", "branch_name",
            "category", "category_name",
            "employee", "employee_name",
            "notes",
        ]
