"""The first-visit intake, section by section.

The sections mirror the wizard's steps — personal, visit, history, referral,
consent — so a validation error comes back addressed to the step that has to
fix it. Values for every choice are codes; the words are the frontend's.
"""

from datetime import date

from rest_framework import serializers

from api.relations import TenantScopedRelatedField
from branches.models import Branch
from employees.models import Employee, Specialization
from medical.models import (
    Allergy,
    ChronicCondition,
    PatientCondition,
    PatientIntake,
    PatientMedicalProfile,
)
from patients.intake import normalize_phone
from patients.models import Patient

from .common import ClinicSerializer


def _phone(value, required):
    digits = normalize_phone(value)
    if not digits:
        if required:
            raise serializers.ValidationError("رقم الهاتف مطلوب.")
        return ""
    if len(digits.lstrip("+")) < 8:
        raise serializers.ValidationError("رقم الهاتف غير صحيح.")
    return digits


class PersonalSection(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    gender = serializers.ChoiceField(choices=Patient.GENDER_CHOICES)
    birth_date = serializers.DateField(required=False, allow_null=True)
    marital_status = serializers.ChoiceField(
        choices=Patient.MARITAL_STATUS_CHOICES, required=False, default="single"
    )
    phone1 = serializers.CharField(max_length=32)
    whatsapp = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True, default=None)
    national_id = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    governorate = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    area = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    address = serializers.CharField(required=False, allow_blank=True, default="")
    branch = TenantScopedRelatedField(model=Branch, required=False, allow_null=True)
    emergency_contact_name = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    emergency_contact_phone = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    emergency_contact_relation = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")

    def validate_name(self, value):
        value = value.strip()
        if len(value) < 3:
            raise serializers.ValidationError("اكتب الاسم كاملاً.")
        return value

    def validate_birth_date(self, value):
        if value and value > date.today():
            raise serializers.ValidationError("تاريخ الميلاد في المستقبل.")
        if value and date.today().year - value.year > 130:
            raise serializers.ValidationError("تاريخ الميلاد غير منطقي.")
        return value

    def validate_phone1(self, value):
        return _phone(value, required=True)

    def validate_whatsapp(self, value):
        return _phone(value, required=False)

    def validate_emergency_contact_phone(self, value):
        return _phone(value, required=False)

    def validate_national_id(self, value):
        value = (value or "").strip()
        if value and not value.isdigit():
            raise serializers.ValidationError("الرقم القومي أرقام فقط.")
        return value

    def validate_email(self, value):
        return value or None


class VisitSection(serializers.Serializer):
    case_type = serializers.ChoiceField(
        choices=PatientIntake.CaseType.choices, default=PatientIntake.CaseType.CONSULTATION
    )
    reason_for_visit = serializers.CharField(max_length=2000)
    symptoms = serializers.CharField(max_length=4000, required=False, allow_blank=True, default="")
    symptom_onset = serializers.ChoiceField(
        choices=PatientIntake.Onset.choices, required=False, allow_blank=True, default=""
    )
    reported_diagnosis = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")
    specialization = TenantScopedRelatedField(model=Specialization, required=False, allow_null=True)
    requested_doctor = TenantScopedRelatedField(model=Employee, required=False, allow_null=True)

    def validate_reason_for_visit(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("اكتب سبب الزيارة.")
        return value

    def validate_requested_doctor(self, doctor):
        if doctor is not None and getattr(doctor.employee_type, "name", None) != "Doctor":
            raise serializers.ValidationError("اختر طبيباً.")
        return doctor

    def validate(self, attrs):
        doctor, specialization = attrs.get("requested_doctor"), attrs.get("specialization")
        if doctor and specialization:
            if not doctor.specializations.filter(pk=specialization.pk).exists():
                raise serializers.ValidationError(
                    {"requested_doctor": "الطبيب المختار لا يتبع هذا التخصص."}
                )
        return attrs


class ConditionEntry(serializers.Serializer):
    condition = serializers.ChoiceField(choices=ChronicCondition.choices)
    other_name = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    details = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")
    current_treatment = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")

    def validate(self, attrs):
        if attrs["condition"] == ChronicCondition.OTHER and not attrs.get("other_name", "").strip():
            raise serializers.ValidationError({"other_name": "اكتب اسم المرض."})
        return attrs


class AllergyEntry(serializers.Serializer):
    substance = serializers.CharField(max_length=200)
    reaction = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    severity = serializers.ChoiceField(choices=Allergy.Severity.choices, default=Allergy.Severity.MODERATE)


class HistorySection(serializers.Serializer):
    smoking_status = serializers.ChoiceField(
        choices=PatientMedicalProfile.Smoking.choices, required=False, allow_blank=True, default=""
    )
    current_medications = serializers.CharField(required=False, allow_blank=True, default="")
    previous_surgeries = serializers.CharField(required=False, allow_blank=True, default="")
    previous_hospitalizations = serializers.CharField(required=False, allow_blank=True, default="")
    family_history = serializers.CharField(required=False, allow_blank=True, default="")
    conditions = ConditionEntry(many=True, required=False, default=list)
    allergies = AllergyEntry(many=True, required=False, default=list)

    def validate_conditions(self, rows):
        seen = set()
        for row in rows:
            if row["condition"] != ChronicCondition.OTHER:
                if row["condition"] in seen:
                    raise serializers.ValidationError("مرض مكرر في القائمة.")
                seen.add(row["condition"])
        return rows

    def validate_allergies(self, rows):
        names = [row["substance"].strip().lower() for row in rows]
        if len(names) != len(set(names)):
            raise serializers.ValidationError("حساسية مكررة في القائمة.")
        return rows


class ReferralSection(serializers.Serializer):
    referral_source = serializers.ChoiceField(
        choices=Patient.ReferralSource.choices, required=False, allow_blank=True, default=""
    )
    referral_detail = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    referring_doctor_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    referred_by_patient = TenantScopedRelatedField(
        model=Patient, branch_field="branch", required=False, allow_null=True
    )
    recommended_doctor = TenantScopedRelatedField(model=Employee, required=False, allow_null=True)

    def validate(self, attrs):
        source = attrs.get("referral_source")
        if source == Patient.ReferralSource.DOCTOR_REFERRAL and not attrs.get("referring_doctor_name", "").strip():
            raise serializers.ValidationError({"referring_doctor_name": "اكتب اسم الطبيب المُحيل."})
        if source == Patient.ReferralSource.OTHER and not attrs.get("referral_detail", "").strip():
            raise serializers.ValidationError({"referral_detail": "وضّح كيف عرفت بنا."})
        return attrs


class PortalReferralSection(ReferralSection):
    """The public form cannot point at an existing patient by identifier —
    that would let anyone probe who is a patient. A name in the text field
    serves the same purpose for the front desk."""

    referred_by_patient = None


class ConsentSection(serializers.Serializer):
    data_processing = serializers.BooleanField()
    contact_by_phone = serializers.BooleanField(required=False, default=True)
    contact_by_whatsapp = serializers.BooleanField(required=False, default=False)
    contact_by_sms = serializers.BooleanField(required=False, default=False)
    contact_by_email = serializers.BooleanField(required=False, default=False)

    def validate_data_processing(self, value):
        if value is not True:
            raise serializers.ValidationError("الموافقة على حفظ البيانات الطبية مطلوبة للتسجيل.")
        return value


class IntakeRegistrationSerializer(serializers.Serializer):
    personal = PersonalSection()
    visit = VisitSection()
    history = HistorySection(required=False)
    referral = ReferralSection(required=False)
    consent = ConsentSection()
    # Set by the front desk after seeing the possible duplicates and deciding
    # this really is a different person.
    confirm_new = serializers.BooleanField(required=False, default=False)


class PortalRegistrationSerializer(IntakeRegistrationSerializer):
    referral = PortalReferralSection(required=False)
    confirm_new = None


# ------------------------------------------------------------------- reads


class PatientConditionSerializer(ClinicSerializer):
    class Meta:
        model = PatientCondition
        fields = ["uuid", "condition", "other_name", "details", "current_treatment", "recorded_at"]
        read_only_fields = ["recorded_at"]


class MedicalHistorySerializer(serializers.Serializer):
    """Profile + conditions, read and replaced together — they are answered
    together, and replacing the condition list wholesale is the only way
    "the patient no longer has X" can be recorded."""

    smoking_status = serializers.ChoiceField(
        choices=PatientMedicalProfile.Smoking.choices, required=False, allow_blank=True, default=""
    )
    current_medications = serializers.CharField(required=False, allow_blank=True, default="")
    previous_surgeries = serializers.CharField(required=False, allow_blank=True, default="")
    previous_hospitalizations = serializers.CharField(required=False, allow_blank=True, default="")
    family_history = serializers.CharField(required=False, allow_blank=True, default="")
    conditions_reviewed = serializers.BooleanField(required=False, default=True)
    conditions = ConditionEntry(many=True, required=False, default=list)

    validate_conditions = HistorySection.validate_conditions


class PatientIntakeSerializer(ClinicSerializer):
    patient_name = serializers.CharField(source="patient.name", read_only=True)
    patient = serializers.UUIDField(source="patient.uuid", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)
    specialization_name = serializers.CharField(source="specialization.name", read_only=True, default=None)
    requested_doctor_name = serializers.CharField(source="requested_doctor.name", read_only=True, default=None)

    class Meta:
        model = PatientIntake
        fields = [
            "uuid", "patient", "patient_name", "branch_name", "case_type",
            "specialization_name", "requested_doctor_name", "reason_for_visit",
            "symptoms", "symptom_onset", "reported_diagnosis", "source", "created_at",
        ]
        read_only_fields = fields
