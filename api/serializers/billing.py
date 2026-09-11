"""Payments in, expenses out."""

from rest_framework import serializers

from api.relations import TenantScopedRelatedField
from appointments.models import Appointment
from billing.models import (
    DoctorCommission,
    DoctorServiceRate,
    Expense,
    ExpenseCategory,
    Payment,
    PaymentMethod,
)
from branches.models import Branch
from employees.models import Employee
from patients.models import Patient
from services.models import Service

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
    voided_by_name = serializers.CharField(source="voided_by.username", read_only=True, default=None)

    class Meta:
        model = Payment
        fields = [
            "uuid", "receipt_number", "amount",
            "appointment", "appointment_serial",
            "patient", "patient_name",
            "method", "method_name",
            "branch", "branch_name",
            "date", "notes",
            "voided_at", "void_reason", "voided_by_name",
        ]
        read_only_fields = ["date", "voided_at", "void_reason"]

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
    category = TenantScopedRelatedField(
        model=ExpenseCategory, required=False, allow_null=True
    )
    employee = TenantScopedRelatedField(
        model=Employee, required=False, allow_null=True, branch_field="branch"
    )
    method = TenantScopedRelatedField(
        model=PaymentMethod, required=False, allow_null=True
    )
    # Inside a cash shift the server sets it to today (api/views/billing.py);
    # outside one — the Owner — it defaults to today when left out.
    date = serializers.DateField(required=False)
    # Inside a shift the branch is the shift's; otherwise it is required.
    branch = TenantScopedRelatedField(model=Branch, required=False)

    branch_name = serializers.CharField(source="branch.name", read_only=True)
    category_name = serializers.CharField(
        source="category.name", read_only=True, default=None
    )
    employee_name = serializers.CharField(
        source="employee.name", read_only=True, default=None
    )
    method_name = serializers.CharField(source="method.name", read_only=True, default=None)
    voided_by_name = serializers.CharField(source="voided_by.username", read_only=True, default=None)

    class Meta:
        model = Expense
        fields = [
            "uuid", "amount", "date",
            "branch", "branch_name",
            "category", "category_name",
            "employee", "employee_name",
            "method", "method_name",
            "notes",
            "voided_at", "void_reason", "voided_by_name",
        ]
        read_only_fields = ["voided_at", "void_reason"]
        # Taken from the recorder's cash shift; otherwise required in create().
        server_filled = ("branch",)

    def create(self, validated_data):
        from django.utils import timezone

        validated_data.setdefault("date", timezone.now().date())
        if validated_data.get("branch") is None:
            raise serializers.ValidationError({"branch": "اختر الفرع."})
        return super().create(validated_data)


class DoctorServiceRateSerializer(ClinicSerializer):
    """One contract line. Written by management only (the view enforces it)."""

    doctor = TenantScopedRelatedField(model=Employee)
    service = TenantScopedRelatedField(model=Service)
    doctor_name = serializers.CharField(source="doctor.name", read_only=True)
    service_name = serializers.CharField(source="service.name", read_only=True)
    service_base_price = serializers.DecimalField(
        source="service.base_price", max_digits=10, decimal_places=2, read_only=True
    )

    class Meta:
        model = DoctorServiceRate
        fields = [
            "uuid", "doctor", "doctor_name", "service", "service_name",
            "service_base_price", "price", "commission_percent", "is_active",
            "notes", "updated_at",
        ]

    def validate_doctor(self, doctor):
        if getattr(doctor.employee_type, "name", None) != "Doctor":
            raise serializers.ValidationError("التعاقد يكون مع طبيب فقط.")
        return doctor

    def validate(self, attrs):
        doctor = attrs.get("doctor", getattr(self.instance, "doctor", None))
        service = attrs.get("service", getattr(self.instance, "service", None))
        clash = DoctorServiceRate.objects.filter(doctor=doctor, service=service)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError({"service": "لهذا الطبيب سطر تعاقد لهذه الخدمة بالفعل."})
        return attrs


class DoctorCommissionSerializer(ClinicSerializer):
    doctor_name = serializers.CharField(source="doctor.name", read_only=True)
    patient_name = serializers.CharField(source="patient.name", read_only=True, default=None)
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)
    receipt_number = serializers.CharField(source="payment.receipt_number", read_only=True, default=None)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    settled_by_name = serializers.CharField(source="settled_by.username", read_only=True, default=None)

    class Meta:
        model = DoctorCommission
        fields = [
            "uuid", "doctor_name", "patient_name", "branch_name", "receipt_number",
            "description", "original_price", "paid_amount", "percent", "amount",
            "status", "status_label", "created_at", "settled_at", "settled_by_name",
        ]
        read_only_fields = fields
