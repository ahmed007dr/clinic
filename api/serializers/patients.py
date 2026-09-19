"""Patients — the record every other clinical and financial row hangs off."""

from rest_framework import serializers

from api.relations import TenantScopedRelatedField
from branches.models import Branch
from employees.models import Employee
from patients.models import Patient

from .common import ClinicSerializer

#: What a clinic sees of a patient who belongs to another clinic and is only
#: here for a confirmed booking (docs/15, D10): enough to receive, call and
#: treat them — no notes, national id, address, contacts, referral or consent.
VISITING_FIELDS = (
    "uuid", "serial_number", "name", "gender", "birth_date", "age", "phone1",
    "branch", "branch_name",
)


class VisitingLimitMixin:
    def to_representation(self, patient):
        from accounts.roles import is_visiting_patient

        data = super().to_representation(patient)
        user = self.request_user
        if user is not None and getattr(user, "is_authenticated", False) and is_visiting_patient(patient, user):
            limited = {name: data[name] for name in VISITING_FIELDS if name in data}
            limited["visiting"] = True
            return limited
        return data


class PatientListSerializer(VisitingLimitMixin, ClinicSerializer):
    """The columns a list screen renders, and no more.

    Deliberately narrower than the detail serializer: a list of five hundred
    patients should not carry five hundred addresses and national IDs across
    the wire to render a table of names and phone numbers.
    """

    branch_name = serializers.CharField(
        source="branch.name", read_only=True, default=None
    )

    class Meta:
        model = Patient
        fields = [
            "uuid", "serial_number", "name", "gender", "phone1",
            "branch", "branch_name", "created_at",
            "needs_review", "registration_source",
        ]
        read_only_fields = fields


class PatientSerializer(VisitingLimitMixin, ClinicSerializer):
    branch = TenantScopedRelatedField(model=Branch, required=False, allow_null=True)
    branch_name = serializers.CharField(
        source="branch.name", read_only=True, default=None
    )
    recommended_doctor = TenantScopedRelatedField(model=Employee, required=False, allow_null=True)
    recommended_doctor_name = serializers.CharField(
        source="recommended_doctor.name", read_only=True, default=None
    )
    age = serializers.SerializerMethodField()
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model = Patient
        fields = [
            "uuid", "serial_number", "name", "national_id",
            "gender", "marital_status", "birth_date", "age",
            "phone1", "phone2", "email", "address",
            "photo", "photo_url", "notes",
            "branch", "branch_name",
            "whatsapp", "governorate", "area",
            "emergency_contact_name", "emergency_contact_phone", "emergency_contact_relation",
            "referral_source", "referral_detail", "referring_doctor_name",
            "recommended_doctor", "recommended_doctor_name",
            "consent_data_processing_at", "contact_by_phone", "contact_by_whatsapp",
            "contact_by_sms", "contact_by_email",
            "registration_source", "needs_review",
            "created_at", "updated_at",
        ]
        read_only_fields = ["consent_data_processing_at", "registration_source", "needs_review"]
        extra_kwargs = {"photo": {"write_only": True, "required": False}}

    def get_age(self, patient):
        """Computed here so every screen shows the same number.

        Doing it in the client means each screen re-derives it and they drift;
        doing it in the database means a migration to add a column that is
        wrong the next morning.
        """
        from datetime import date

        if not patient.birth_date:
            return None
        today = date.today()
        born = patient.birth_date
        return today.year - born.year - (
            (today.month, today.day) < (born.month, born.day)
        )

    def get_photo_url(self, patient):
        if not patient.photo:
            return None
        request = self.context.get("request")
        url = patient.photo.url
        return request.build_absolute_uri(url) if request else url
