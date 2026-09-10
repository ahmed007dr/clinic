"""Appointments — the booking, not the encounter.

An Appointment records that someone was *scheduled*. What actually happened is
a `medical.Visit`, and the two are separate on purpose: walk-ins have no
appointment, and a booking nobody attended produces no visit.
"""

from rest_framework import serializers

from api.relations import TenantScopedRelatedField
from appointments.models import Appointment
from branches.models import Branch
from employees.models import Employee, Specialization
from patients.models import Patient
from services.models import Service

from .common import ClinicSerializer


class AppointmentSerializer(ClinicSerializer):
    # Branch-scoped: a receptionist who cannot see a patient must not be able
    # to book for them by pasting a UUID. See api/relations.py.
    patient = TenantScopedRelatedField(model=Patient, branch_field="branch")
    doctor = TenantScopedRelatedField(
        model=Employee, required=False, allow_null=True
    )
    specialization = TenantScopedRelatedField(
        model=Specialization, required=False, allow_null=True
    )
    service = TenantScopedRelatedField(
        model=Service, required=False, allow_null=True
    )
    branch = TenantScopedRelatedField(model=Branch, required=False, allow_null=True)

    patient_name = serializers.CharField(source="patient.name", read_only=True)
    patient_phone = serializers.CharField(
        source="patient.phone1", read_only=True, default=None
    )
    doctor_name = serializers.CharField(
        source="doctor.name", read_only=True, default=None
    )
    service_name = serializers.CharField(
        source="service.name", read_only=True, default=None
    )
    branch_name = serializers.CharField(
        source="branch.name", read_only=True, default=None
    )
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Appointment
        fields = [
            "uuid", "serial_number",
            "patient", "patient_name", "patient_phone",
            "doctor", "doctor_name",
            "specialization",
            "service", "service_name",
            "branch", "branch_name",
            "status", "status_label",
            "scheduled_date", "price", "notes", "created_at",
        ]

    def validate_doctor(self, doctor):
        """Only staff typed as Doctor may hold an appointment.

        The model expresses this with `limit_choices_to`, which constrains the
        admin and ModelForm dropdowns and nothing else — a direct API write
        would sail past it and book a patient with the cleaner.
        """
        if doctor is None:
            return doctor
        type_name = getattr(doctor.employee_type, "name", None)
        if type_name != "Doctor":
            raise serializers.ValidationError(
                "لا يمكن حجز موعد إلا مع طبيب."
            )
        return doctor
