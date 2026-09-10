"""First-visit registration — one implementation behind two doors.

Staff at the front desk (`api/views/intake.py`) and a patient registering
themselves online (`portal/registration.py`) both end here, so the rules — what
a registration creates, what counts as a duplicate, how a self-registration is
confirmed, merged or rejected — exist exactly once.

Every function runs inside the caller's tenant context; nothing here chooses a
tenant.
"""

from django.db import transaction
from django.db.models import F, ProtectedError, Q, Value
from django.db.models.functions import Replace
from django.utils import timezone

from appointments.models import Appointment
from medical.models import Allergy, PatientCondition, PatientIntake, PatientMedicalProfile
from subscriptions.entitlements import check_limit

from .models import Patient

PROFILE_FIELDS = (
    "smoking_status",
    "current_medications",
    "previous_surgeries",
    "previous_hospitalizations",
    "family_history",
)

# Filled on the surviving record from a merged self-registration when the
# surviving record has nothing there yet.
MERGEABLE_PATIENT_FIELDS = (
    "whatsapp", "email", "governorate", "area", "address",
    "emergency_contact_name", "emergency_contact_phone", "emergency_contact_relation",
    "referral_source", "referral_detail", "referring_doctor_name", "recommended_doctor",
)


class RegistrationError(Exception):
    """A registration action that cannot proceed, with a message for people."""


def normalize_phone(value):
    """Digits only (keeping a leading +), so '010 0000 0001' and '01000000001'
    are recognised as the same number."""
    raw = str(value or "").strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    if raw.startswith("+") and digits:
        return "+" + digits
    return digits


def confirmed_patients():
    """Patients who count against the plan.

    A self-registration awaiting review does not: a form anyone can submit
    must not be able to exhaust a clinic's patient allowance.
    """
    return Patient.objects.filter(needs_review=False)


def _digits(field):
    """The stored number without the separators people type."""
    expression = F(field)
    for separator in (" ", "-", "(", ")", "."):
        expression = Replace(expression, Value(separator), Value(""))
    return expression


def duplicate_candidates(*, phone="", whatsapp="", national_id="", exclude_pk=None):
    """Existing patients of this group sharing a phone number or national ID."""
    query = Q()
    numbers = {normalize_phone(value) for value in (phone, whatsapp)} - {""}
    for number in numbers:
        # Older records were stored as typed, spaces and dashes included.
        query |= Q(_phone1=number) | Q(_phone2=number) | Q(_whatsapp=number)
    nid = str(national_id or "").strip()
    if nid:
        query |= Q(national_id=nid)
    if not query:
        return Patient.objects.none()
    candidates = Patient.objects.annotate(
        _phone1=_digits("phone1"), _phone2=_digits("phone2"), _whatsapp=_digits("whatsapp"),
    ).filter(query)
    if exclude_pk:
        candidates = candidates.exclude(pk=exclude_pk)
    return candidates


def check_doctor_branch(doctor, branch):
    """The doctor a patient asks for must work at the clinic they are
    registering with; otherwise the request lands at a desk that cannot book it."""
    if doctor is not None and branch is not None and doctor.branch_id != branch.pk:
        raise RegistrationError("الطبيب المختار لا يعمل في هذه العيادة.")


@transaction.atomic
def register_patient(*, tenant, personal, visit, consent, history=None, referral=None,
                     actor=None, source=Patient.RegistrationSource.STAFF):
    """Create the patient and everything the intake collected, all or nothing."""
    personal = dict(personal)
    referral = dict(referral or {})
    history = dict(history or {})
    conditions = history.pop("conditions", [])
    allergies = history.pop("allergies", [])

    for field in ("phone1", "whatsapp", "emergency_contact_phone"):
        if personal.get(field):
            personal[field] = normalize_phone(personal[field])

    self_registered = source == Patient.RegistrationSource.PORTAL
    patient = Patient.objects.create(
        tenant=tenant,
        **personal,
        **referral,
        consent_data_processing_at=timezone.now() if consent.get("data_processing") else None,
        contact_by_phone=consent.get("contact_by_phone", True),
        contact_by_whatsapp=consent.get("contact_by_whatsapp", False),
        contact_by_sms=consent.get("contact_by_sms", False),
        contact_by_email=consent.get("contact_by_email", False),
        registration_source=source,
        needs_review=self_registered,
    )

    if history or conditions or allergies:
        PatientMedicalProfile.objects.create(
            tenant=tenant, patient=patient, updated_by=actor,
            # The history step was answered, so an empty condition list means
            # "none" rather than "never asked".
            conditions_reviewed=True,
            **{field: history.get(field, "") for field in PROFILE_FIELDS},
        )
    for condition in conditions:
        PatientCondition.objects.create(tenant=tenant, patient=patient, recorded_by=actor, **condition)
    for allergy in allergies:
        Allergy.objects.create(tenant=tenant, patient=patient, recorded_by=actor, **allergy)

    intake = PatientIntake.objects.create(
        tenant=tenant,
        patient=patient,
        branch=patient.branch,
        source=PatientIntake.Source.PORTAL if self_registered else PatientIntake.Source.STAFF,
        created_by=actor,
        **visit,
    )
    return patient, intake


def confirm_registration(patient, tenant):
    """Accept a self-registration as a patient of the group."""
    if not patient.needs_review:
        return patient
    # Counted only now: this is the moment it becomes a patient on the plan.
    check_limit(tenant, "max_patients", confirmed_patients().count())
    patient.needs_review = False
    patient.save(update_fields=["needs_review"])
    return patient


@transaction.atomic
def merge_registration(source, target):
    """Fold a self-registration into the patient it turned out to be.

    Only a pending self-registration can be merged away — a confirmed patient
    may carry clinical records, and silently moving those is not a front-desk
    decision.
    """
    if not source.needs_review:
        raise RegistrationError("يمكن دمج التسجيلات الذاتية غير المؤكدة فقط.")
    if source.pk == target.pk:
        raise RegistrationError("لا يمكن دمج المريض في نفسه.")

    PatientIntake.objects.filter(patient=source).update(patient=target)
    Appointment.objects.filter(patient=source).update(patient=target)

    for condition in PatientCondition.objects.filter(patient=source):
        clash = (
            condition.condition != "other"
            and PatientCondition.objects.filter(patient=target, condition=condition.condition).exists()
        )
        if clash:
            condition.delete()
        else:
            condition.patient = target
            condition.save(update_fields=["patient"])

    for allergy in Allergy.objects.filter(patient=source):
        if Allergy.objects.filter(patient=target, substance__iexact=allergy.substance).exists():
            allergy.delete()
        else:
            allergy.patient = target
            allergy.save(update_fields=["patient"])

    theirs = PatientMedicalProfile.objects.filter(patient=source).first()
    ours = PatientMedicalProfile.objects.filter(patient=target).first()
    if theirs and not ours:
        theirs.patient = target
        theirs.save(update_fields=["patient"])
    elif theirs and ours:
        for field in PROFILE_FIELDS:
            if not getattr(ours, field) and getattr(theirs, field):
                setattr(ours, field, getattr(theirs, field))
        ours.conditions_reviewed = ours.conditions_reviewed or theirs.conditions_reviewed
        ours.save()
        theirs.delete()

    changed = []
    for field in MERGEABLE_PATIENT_FIELDS:
        if not getattr(target, field) and getattr(source, field):
            setattr(target, field, getattr(source, field))
            changed.append(field)
    if target.consent_data_processing_at is None and source.consent_data_processing_at:
        target.consent_data_processing_at = source.consent_data_processing_at
        for field in ("contact_by_phone", "contact_by_whatsapp", "contact_by_sms", "contact_by_email"):
            setattr(target, field, getattr(source, field))
            changed.append(field)
        changed.append("consent_data_processing_at")
    if changed:
        target.save(update_fields=changed)

    try:
        source.delete()
    except ProtectedError:
        raise RegistrationError("هذا التسجيل مرتبط بسجلات لا يمكن نقلها.")
    return target


@transaction.atomic
def reject_registration(source):
    """Discard a self-registration and everything it created."""
    if not source.needs_review:
        raise RegistrationError("يمكن رفض التسجيلات الذاتية غير المؤكدة فقط.")
    PatientIntake.objects.filter(patient=source).delete()
    PatientCondition.objects.filter(patient=source).delete()
    Allergy.objects.filter(patient=source).delete()
    PatientMedicalProfile.objects.filter(patient=source).delete()
    Appointment.objects.filter(patient=source, status="requested").delete()
    try:
        source.delete()
    except ProtectedError:
        raise RegistrationError("هذا التسجيل مرتبط بسجلات لا يمكن حذفها.")
