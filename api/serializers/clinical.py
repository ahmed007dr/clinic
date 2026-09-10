"""Clinical records: visits, prescriptions, plans, sessions, procedures, labs, files.

Everything in this module is gated by `CanViewClinical` at the view layer.
Reception never reaches these serializers at all — the protection is that the
endpoints refuse them, not that the fields are hidden, because a hidden field
is one `fields = "__all__"` away from being visible again.
"""

from rest_framework import serializers

from api.relations import TenantScopedRelatedField
from branches.models import Branch
from employees.models import Employee
from medical.models import (
    Allergy,
    LabResult,
    MedicalAttachment,
    Procedure,
    Prescription,
    PrescriptionItem,
    TreatmentPlan,
    TreatmentSession,
    Visit,
)
from patients.models import Patient
from services.models import Service

from .common import ClinicSerializer


class VisitMatchesPatient:
    """A clinical record's visit must be the same patient's visit.

    Nothing in the schema ties the two together, so without this a
    prescription for one patient can be filed under another patient's visit —
    and then appears in the wrong person's history, which is worse than being
    lost.
    """

    def validate(self, attrs):
        attrs = super().validate(attrs)
        visit = attrs.get("visit", getattr(self.instance, "visit", None))
        patient = attrs.get("patient") or getattr(self.instance, "patient", None)
        if visit and patient and visit.patient_id != patient.pk:
            raise serializers.ValidationError(
                {"visit": "الزيارة المختارة لا تخص هذا المريض."}
            )
        return attrs


class VisitSerializer(ClinicSerializer):
    patient = TenantScopedRelatedField(model=Patient, branch_field="branch")
    doctor = TenantScopedRelatedField(model=Employee, required=False, allow_null=True)
    branch = TenantScopedRelatedField(model=Branch, required=False, allow_null=True)

    patient_name = serializers.CharField(source="patient.name", read_only=True)
    patient_serial = serializers.CharField(
        source="patient.serial_number", read_only=True
    )
    doctor_name = serializers.CharField(
        source="doctor.name", read_only=True, default=None
    )
    branch_name = serializers.CharField(
        source="branch.name", read_only=True, default=None
    )

    class Meta:
        model = Visit
        fields = [
            "uuid", "serial_number",
            "patient", "patient_name", "patient_serial",
            "doctor", "doctor_name",
            "branch", "branch_name",
            "visit_date", "chief_complaint", "examination",
            "diagnosis", "treatment_plan", "follow_up_date",
            "created_at", "updated_at",
        ]


class PrescriptionItemSerializer(ClinicSerializer):
    """Written only as part of its prescription — see the parent below."""

    class Meta:
        model = PrescriptionItem
        fields = [
            "uuid", "medication", "dosage", "frequency", "duration", "instructions",
        ]


class PrescriptionSerializer(VisitMatchesPatient, ClinicSerializer):
    """A prescription and its medicines in one request.

    Nested and writable on purpose: a prescription with no items is not a
    partial record, it is a clinical mistake, and two round trips is exactly
    how you end up with one when the second request fails.
    """

    visit = TenantScopedRelatedField(model=Visit, branch_field="branch")
    patient = TenantScopedRelatedField(model=Patient, branch_field="branch")
    doctor = TenantScopedRelatedField(model=Employee, required=False, allow_null=True)
    items = PrescriptionItemSerializer(many=True)

    patient_name = serializers.CharField(source="patient.name", read_only=True)
    doctor_name = serializers.CharField(
        source="doctor.name", read_only=True, default=None
    )
    allergy_warnings = serializers.SerializerMethodField()

    class Meta:
        model = Prescription
        fields = [
            "uuid", "serial_number",
            "visit", "patient", "patient_name",
            "doctor", "doctor_name",
            "issued_at", "notes", "items", "created_at",
            "allergy_warnings",
        ]

    def get_allergy_warnings(self, prescription):
        """Medicines on this prescription that mention a recorded allergen.

        The same `allergy_conflicts` the server-rendered screens use — one
        definition of "this clashes", so the two front ends cannot disagree on
        a patient-safety check. It warns and does not block: §26 keeps the
        decision with the doctor.
        """
        from medical.models import allergy_conflicts

        return [
            {"medication": medication, "allergen": allergen}
            for medication, allergen in allergy_conflicts(
                prescription.patient,
                [item.medication for item in prescription.items.all()],
            )
        ]

    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError("يجب إضافة دواء واحد على الأقل.")
        return items

    def create(self, validated_data):
        items = validated_data.pop("items", [])
        tenant = validated_data["tenant"]
        prescription = Prescription.objects.create(**validated_data)
        # Each item carries the tenant explicitly: PrescriptionItem is
        # tenant-owned in its own right, and under row-level security an insert
        # with no tenant is rejected outright rather than silently orphaned.
        PrescriptionItem.objects.bulk_create(
            [
                PrescriptionItem(prescription=prescription, tenant=tenant, **item)
                for item in items
            ]
        )
        return prescription

    def update(self, instance, validated_data):
        items = validated_data.pop("items", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        if items is not None:
            # Replace wholesale. Diffing medicine lines by position invents
            # identity where none exists and silently rewrites the wrong row
            # when one is removed from the middle.
            instance.items.all().delete()
            PrescriptionItem.objects.bulk_create(
                [
                    PrescriptionItem(
                        prescription=instance, tenant=instance.tenant, **item
                    )
                    for item in items
                ]
            )
        return instance


class TreatmentPlanSerializer(VisitMatchesPatient, ClinicSerializer):
    patient = TenantScopedRelatedField(model=Patient, branch_field="branch")
    visit = TenantScopedRelatedField(
        model=Visit, branch_field="branch", required=False, allow_null=True
    )
    doctor = TenantScopedRelatedField(model=Employee, required=False, allow_null=True)
    branch = TenantScopedRelatedField(model=Branch, required=False, allow_null=True)
    service = TenantScopedRelatedField(model=Service, required=False, allow_null=True)

    patient_name = serializers.CharField(source="patient.name", read_only=True)
    doctor_name = serializers.CharField(
        source="doctor.name", read_only=True, default=None
    )
    service_name = serializers.CharField(
        source="service.name", read_only=True, default=None
    )
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    completed_sessions = serializers.SerializerMethodField()

    class Meta:
        model = TreatmentPlan
        fields = [
            "uuid", "serial_number", "title",
            "patient", "patient_name",
            "visit", "doctor", "doctor_name",
            "branch", "service", "service_name",
            "planned_sessions", "completed_sessions",
            "status", "status_label", "start_date", "notes",
            "created_at", "updated_at",
        ]

    def get_completed_sessions(self, plan):
        """Progress is what the plan screen is for, so it ships with the plan
        rather than costing a second request per row."""
        return plan.sessions.filter(
            status=TreatmentSession.Status.COMPLETED
        ).count()


class TreatmentSessionSerializer(ClinicSerializer):
    plan = TenantScopedRelatedField(model=TreatmentPlan, branch_field="branch")
    patient = TenantScopedRelatedField(model=Patient, branch_field="branch")
    doctor = TenantScopedRelatedField(model=Employee, required=False, allow_null=True)
    branch = TenantScopedRelatedField(model=Branch, required=False, allow_null=True)
    service = TenantScopedRelatedField(model=Service, required=False, allow_null=True)

    plan_title = serializers.CharField(source="plan.title", read_only=True)
    patient_name = serializers.CharField(source="patient.name", read_only=True)
    doctor_name = serializers.CharField(
        source="doctor.name", read_only=True, default=None
    )
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = TreatmentSession
        fields = [
            "uuid", "plan", "plan_title",
            "patient", "patient_name",
            "doctor", "doctor_name",
            "branch", "service",
            "sequence", "scheduled_date", "performed_at",
            "status", "status_label",
            "quantity", "unit_price", "discount",
            "result", "notes", "created_at", "updated_at",
        ]

    def validate(self, attrs):
        plan = attrs.get("plan") or getattr(self.instance, "plan", None)
        patient = attrs.get("patient") or getattr(self.instance, "patient", None)
        if plan and patient and plan.patient_id != patient.pk:
            raise serializers.ValidationError(
                {"patient": "المريض لا يطابق مريض خطة العلاج."}
            )
        return attrs


class ProcedureSerializer(VisitMatchesPatient, ClinicSerializer):
    visit = TenantScopedRelatedField(model=Visit, branch_field="branch")
    patient = TenantScopedRelatedField(model=Patient, branch_field="branch")
    doctor = TenantScopedRelatedField(model=Employee, required=False, allow_null=True)
    branch = TenantScopedRelatedField(model=Branch, required=False, allow_null=True)
    service = TenantScopedRelatedField(model=Service, required=False, allow_null=True)

    patient_name = serializers.CharField(source="patient.name", read_only=True)
    doctor_name = serializers.CharField(
        source="doctor.name", read_only=True, default=None
    )
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Procedure
        fields = [
            "uuid", "serial_number", "name",
            "visit", "patient", "patient_name",
            "doctor", "doctor_name",
            "branch", "service",
            "performed_at", "status", "status_label",
            "body_site", "findings", "outcome", "complications", "notes",
            "quantity", "unit_price", "discount",
            "created_at", "updated_at",
        ]


class LabResultSerializer(VisitMatchesPatient, ClinicSerializer):
    patient = TenantScopedRelatedField(model=Patient, branch_field="branch")
    visit = TenantScopedRelatedField(
        model=Visit, branch_field="branch", required=False, allow_null=True
    )
    ordered_by = TenantScopedRelatedField(
        model=Employee, required=False, allow_null=True
    )
    branch = TenantScopedRelatedField(model=Branch, required=False, allow_null=True)

    patient_name = serializers.CharField(source="patient.name", read_only=True)
    ordered_by_name = serializers.CharField(
        source="ordered_by.name", read_only=True, default=None
    )
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    flag_label = serializers.CharField(source="get_flag_display", read_only=True)
    acknowledged_by_name = serializers.CharField(
        source="acknowledged_by.username", read_only=True, default=None
    )

    class Meta:
        model = LabResult
        fields = [
            "uuid", "serial_number", "test_name", "specimen", "lab_name",
            "patient", "patient_name",
            "visit", "ordered_by", "ordered_by_name", "branch",
            "value", "unit", "reference_range",
            "flag", "flag_label", "status", "status_label",
            "ordered_at", "resulted_at",
            "acknowledged_by", "acknowledged_by_name", "acknowledged_at",
            "notes", "created_at", "updated_at",
        ]
        # Acknowledgement is an act with a named actor and a timestamp, not two
        # fields a client fills in. It has its own endpoint.
        read_only_fields = ["acknowledged_by", "acknowledged_at"]


class MedicalAttachmentSerializer(VisitMatchesPatient, ClinicSerializer):
    patient = TenantScopedRelatedField(model=Patient, branch_field="branch")
    visit = TenantScopedRelatedField(
        model=Visit, branch_field="branch", required=False, allow_null=True
    )
    lab_result = TenantScopedRelatedField(
        model=LabResult, required=False, allow_null=True
    )
    branch = TenantScopedRelatedField(model=Branch, required=False, allow_null=True)

    patient_name = serializers.CharField(source="patient.name", read_only=True)
    category_label = serializers.CharField(
        source="get_category_display", read_only=True
    )
    uploaded_by_name = serializers.CharField(
        source="uploaded_by.username", read_only=True, default=None
    )

    class Meta:
        model = MedicalAttachment
        fields = [
            "uuid", "serial_number", "title",
            "patient", "patient_name",
            "visit", "lab_result", "branch",
            "category", "category_label",
            "file", "original_filename", "content_type", "size_bytes", "checksum",
            "notes", "uploaded_by_name", "created_at",
        ]
        # The stored file is private and streamed by an authenticated view;
        # `file` is accepted on upload and never rendered as a URL, because
        # `PrivateAttachmentStorage.url()` raises by design.
        extra_kwargs = {"file": {"write_only": True}}
        read_only_fields = [
            "original_filename", "content_type", "size_bytes", "checksum",
        ]

    def validate_file(self, uploaded):
        """The same checks `MedicalAttachmentForm.clean_file` performs.

        Not shared with the form by accident of history but re-applied here
        deliberately: an upload endpoint that trusts the declared content type
        accepts an executable named `report.pdf`, and the API is a second front
        door to the same storage. `validate_attachment` reads the leading bytes
        rather than believing the extension.

        The derived columns are computed while the upload is still in hand —
        once the field holds a stored file there is nothing left to hash.
        """
        from pathlib import PurePath

        from django.core.exceptions import ValidationError as DjangoValidationError

        from medical.attachments import checksum, validate_attachment

        if not hasattr(uploaded, "size") or not hasattr(uploaded, "read"):
            return uploaded
        try:
            _extension, content_type = validate_attachment(uploaded)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))

        self._detected = {
            "content_type": content_type,
            "size_bytes": uploaded.size,
            "checksum": checksum(uploaded),
            # Base name only: the browser may send a path, and a stored value
            # containing separators is a trap for anything that later joins it
            # to a directory.
            "original_filename": PurePath(uploaded.name or "").name[:255],
        }
        return uploaded

    def create(self, validated_data):
        validated_data.update(getattr(self, "_detected", {}))
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data.update(getattr(self, "_detected", {}))
        return super().update(instance, validated_data)


class AllergySerializer(ClinicSerializer):
    """A standing fact about the patient, shown on every encounter."""

    patient = TenantScopedRelatedField(model=Patient, branch_field="branch")
    patient_name = serializers.CharField(source="patient.name", read_only=True)
    severity_label = serializers.CharField(source="get_severity_display", read_only=True)
    recorded_by_name = serializers.CharField(
        source="recorded_by.username", read_only=True, default=None
    )

    class Meta:
        model = Allergy
        fields = [
            "uuid", "patient", "patient_name", "substance", "reaction",
            "severity", "severity_label", "notes",
            "recorded_by_name", "recorded_at",
        ]
        read_only_fields = ["recorded_at"]

    def validate(self, attrs):
        """One row per substance per patient — the constraint exists in the
        database, and without this check it surfaces as a 500 instead of a
        message the doctor can act on."""
        patient = attrs.get("patient") or getattr(self.instance, "patient", None)
        substance = (attrs.get("substance") or getattr(self.instance, "substance", "")).strip()
        if patient and substance:
            clash = Allergy.objects.filter(patient=patient, substance__iexact=substance)
            if self.instance:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise serializers.ValidationError(
                    {"substance": "هذه الحساسية مسجلة بالفعل لهذا المريض."}
                )
        return attrs
