"""Creating a portal account, and the account's own profile (docs/15, Phase 2).

**Signing up** — the rule that matters (D5): a new account is linked to an
*existing* patient only after the person proves they can read the e-mail address
**on that patient's file**. Matching on a phone number alone would let anyone who
knows a patient's number open their file.

1. `account/start/` takes the form. It looks for one confirmed patient with the
   same phone number *and* the same name. If that patient has an e-mail on file,
   the code goes **there** — not to the address just typed. Otherwise the code
   goes to the typed address and, once confirmed, a new patient is created in
   quarantine (`needs_review`), which reception confirms or merges with the
   existing file it turns out to duplicate. Either way the answer is the same
   words: nothing tells the caller whether a patient exists.
2. `account/verify/` takes the code, and only then creates the account (and the
   quarantined patient, if any) and signs the person in.

It is a public write path, so it sits behind the same switch as self-registration
(`Tenant.portal_self_registration`, off by default) and is throttled per address
as well as per client.

**The profile** — the patient edits their contact details. A new e-mail address
is proved with a code sent to the *new* address before it replaces the old. A
phone number cannot be changed here: without an SMS provider there is no way to
prove the new one, so it stays the clinic's to change (and doing so ends the
patient's sessions, docs/12).
"""

from datetime import date

from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from branches.models import Branch
from patients.intake import confirmed_patients, duplicate_candidates, normalize_phone
from patients.models import Patient

from . import otp_channels
from .auth import enforce_csrf
from .models import PatientAccount, PortalVerification, hash_token, new_token
from .views import OTP_ERROR, PortalLoginThrottle, PortalView, me_payload, signed_in

#: Codes issued to one address in an hour, past which nothing more is sent.
MAX_CODES_PER_ADDRESS = 5

SIGNUP_SENT = (
    "أرسلنا رمز التأكيد. إن كان لك ملف مسجّل لدى العيادة ببريد إلكتروني فسيصلك الرمز عليه، "
    "وإلا فعلى البريد الذي كتبته."
)
EMAIL_CODE_SENT = "أرسلنا رمز التأكيد إلى البريد الجديد."
CLOSED = "التسجيل الإلكتروني غير متاح لهذه العيادة."


class SignupThrottle(PortalLoginThrottle):
    scope = "portal_signup"


def _same_name(a, b):
    return " ".join(str(a or "").split()).casefold() == " ".join(str(b or "").split()).casefold()


def _digits_only(value):
    return "".join(ch for ch in str(value or "") if ch.isdigit())


class SignupSerializer(serializers.Serializer):
    name = serializers.CharField(min_length=2, max_length=100)
    phone = serializers.CharField(max_length=32)
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(min_length=8, max_length=128, trim_whitespace=False, write_only=True)
    gender = serializers.ChoiceField(choices=Patient.GENDER_CHOICES)
    birth_date = serializers.DateField(required=False, allow_null=True)
    branch = serializers.UUIDField()
    consent = serializers.BooleanField()
    contact_by_email = serializers.BooleanField(required=False, default=True)
    contact_by_whatsapp = serializers.BooleanField(required=False, default=False)
    contact_by_sms = serializers.BooleanField(required=False, default=False)

    def validate_name(self, value):
        return " ".join(value.split())

    def validate_phone(self, value):
        digits = _digits_only(value)
        if not 8 <= len(digits) <= 15:
            raise serializers.ValidationError("رقم الهاتف غير صالح.")
        return normalize_phone(value)

    def validate_email(self, value):
        return value.strip().lower()

    def validate_birth_date(self, value):
        if value is not None and not (date(1900, 1, 1) <= value <= timezone.now().date()):
            raise serializers.ValidationError("تاريخ الميلاد غير صالح.")
        return value

    def validate_consent(self, value):
        if value is not True:
            raise serializers.ValidationError("يجب الموافقة على معالجة البيانات لإنشاء الحساب.")
        return value

    def validate(self, attrs):
        try:
            validate_password(attrs["password"])
        except DjangoValidationError as error:
            raise serializers.ValidationError({"password": list(error.messages)})
        if _digits_only(attrs["password"]) == _digits_only(attrs["phone"]):
            raise serializers.ValidationError({"password": ["كلمة المرور لا تكون رقم الهاتف."]})
        return attrs


def find_link_target(phone, name):
    """The one confirmed patient this signup may be linked to, or None.

    Same phone number **and** the same name, and one patient only: a household
    sharing a number must not have a parent's file offered to a child's signup.
    A patient with no e-mail on file cannot be verified, so is never a target.
    """
    matches = [
        patient
        for patient in duplicate_candidates(phone=phone).filter(needs_review=False)
        if _same_name(patient.name, name)
    ]
    if len(matches) != 1 or not (matches[0].email or "").strip():
        return None
    return matches[0]


class _PublicSignupView(PortalView):
    authentication_classes = []
    permission_classes = [AllowAny]


class SignupStartView(_PublicSignupView):
    throttle_classes = [SignupThrottle]

    def post(self, request, slug):
        enforce_csrf(request)
        if not self.tenant.portal_self_registration:
            return Response({"detail": CLOSED}, status=404)
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        branch = Branch.objects.filter(uuid=data["branch"], is_active=True, about_visible=True).first()
        if branch is None:
            return Response({"branch": ["اختر العيادة."]}, status=400)

        target = find_link_target(data["phone"], data["name"])
        destination = (target.email.strip().lower() if target else data["email"])
        answer = {"ticket": new_token(), "detail": SIGNUP_SENT}

        # One address must not be flooded, whether it is the one typed or the
        # one on a patient's file. Past the limit nothing is sent and the
        # answer looks the same.
        for key, value in (("email", data["email"]), ("destination", destination)):
            if PortalVerification.recent_count(
                purpose=PortalVerification.Purpose.SIGNUP, key=key, key_value=value
            ) >= MAX_CODES_PER_ADDRESS:
                return Response(answer)

        channel = otp_channels.channel_for(self.tenant)
        row, ticket, code = PortalVerification.issue(
            tenant=self.tenant, purpose=PortalVerification.Purpose.SIGNUP, patient=target,
            channel=channel.name,
            data={
                "name": data["name"], "phone": data["phone"], "email": data["email"],
                "gender": data["gender"],
                "birth_date": data["birth_date"].isoformat() if data.get("birth_date") else None,
                "branch": branch.pk,
                "password_hash": make_password(data["password"]),
                "contact_by_email": data["contact_by_email"],
                "contact_by_whatsapp": data["contact_by_whatsapp"],
                "contact_by_sms": data["contact_by_sms"],
                "destination": destination,
            },
        )
        channel.send(
            tenant=self.tenant, branch=branch, destination=destination, code=code, purpose="signup"
        )
        answer["ticket"] = ticket
        return Response(answer)


class SignupVerifyView(_PublicSignupView):
    throttle_classes = [PortalLoginThrottle]

    def post(self, request, slug):
        enforce_csrf(request)
        if not self.tenant.portal_self_registration:
            return Response({"detail": CLOSED}, status=404)
        ticket = str(request.data.get("ticket") or "").strip()
        code = str(request.data.get("code") or "").strip()
        row = (
            PortalVerification.objects.select_related("patient")
            .filter(ticket_hash=hash_token(ticket), purpose=PortalVerification.Purpose.SIGNUP)
            .first()
            if ticket else None
        )
        with transaction.atomic():
            # A wrong guess is counted and kept; only a right one is consumed.
            if row is None or not code or not row.verify(code):
                return Response({"detail": OTP_ERROR}, status=400)
            account = self._create(row)
            return signed_in(self, account, slug, me_payload(self.tenant, account.patient))

    def _create(self, row):
        data = row.data
        patient = row.patient
        if patient is None:
            patient = Patient.objects.create(
                tenant=self.tenant,
                name=data["name"], phone1=data["phone"], email=data["email"],
                gender=data["gender"], birth_date=data["birth_date"],
                branch=Branch.objects.filter(pk=data["branch"]).first(),
                registration_source=Patient.RegistrationSource.PORTAL,
                # The address is proven, the person is not: reception confirms
                # or merges this with the file it duplicates before it counts
                # as a patient (patients.intake).
                needs_review=True,
                consent_data_processing_at=timezone.now(),
                contact_by_phone=True,
                contact_by_email=data["contact_by_email"],
                contact_by_whatsapp=data["contact_by_whatsapp"],
                contact_by_sms=data["contact_by_sms"],
            )
        account, _ = PatientAccount.objects.get_or_create(
            patient=patient, defaults={"tenant": self.tenant}
        )
        # Proof of the file's address is what an e-mail code login already
        # accepts, so setting the password with it is no weaker.
        account.password = data["password_hash"]
        account.is_active = True
        account.failed_logins = 0
        account.locked_until = None
        account.save()
        account.revoke_sessions()
        return account


# ---------------------------------------------------------------- profile

PROFILE_EDITABLE = (
    "address", "governorate", "area", "whatsapp",
    "emergency_contact_name", "emergency_contact_phone", "emergency_contact_relation",
    "contact_by_phone", "contact_by_whatsapp", "contact_by_sms", "contact_by_email",
)


def profile_payload(patient):
    return {
        # Who they are: shown, not editable here.
        "name": patient.name,
        "serial_number": patient.serial_number,
        "phone": patient.phone1 or "",
        "email": patient.email or "",
        "gender": patient.gender,
        "birth_date": patient.birth_date,
        **{field: getattr(patient, field) or ("" if field not in PROFILE_BOOLS else False)
           for field in PROFILE_EDITABLE},
    }


PROFILE_BOOLS = ("contact_by_phone", "contact_by_whatsapp", "contact_by_sms", "contact_by_email")


class ProfileSerializer(serializers.Serializer):
    address = serializers.CharField(required=False, allow_blank=True, max_length=500)
    governorate = serializers.CharField(required=False, allow_blank=True, max_length=100)
    area = serializers.CharField(required=False, allow_blank=True, max_length=100)
    whatsapp = serializers.CharField(required=False, allow_blank=True, max_length=32)
    emergency_contact_name = serializers.CharField(required=False, allow_blank=True, max_length=100)
    emergency_contact_phone = serializers.CharField(required=False, allow_blank=True, max_length=32)
    emergency_contact_relation = serializers.CharField(required=False, allow_blank=True, max_length=50)
    contact_by_phone = serializers.BooleanField(required=False)
    contact_by_whatsapp = serializers.BooleanField(required=False)
    contact_by_sms = serializers.BooleanField(required=False)
    contact_by_email = serializers.BooleanField(required=False)

    def _phone(self, value):
        if not value:
            return ""
        if not 8 <= len(_digits_only(value)) <= 15:
            raise serializers.ValidationError("رقم الهاتف غير صالح.")
        return normalize_phone(value)

    validate_whatsapp = _phone
    validate_emergency_contact_phone = _phone


class ProfileView(PortalView):
    def get(self, request, slug):
        return Response(profile_payload(self.patient))

    def patch(self, request, slug):
        # Only these fields, whatever else is sent: a patient never edits their
        # name, phone number, clinic or anything clinical from here.
        serializer = ProfileSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        patient = self.patient
        changed = []
        for field, value in serializer.validated_data.items():
            setattr(patient, field, value)
            changed.append(field)
        if changed:
            patient.save(update_fields=[*changed, "updated_at"])
        return Response(profile_payload(patient))


class EmailChangeStartView(PortalView):
    throttle_classes = [PortalLoginThrottle]

    def post(self, request, slug):
        serializer = serializers.EmailField(max_length=254)
        try:
            email = serializer.run_validation(request.data.get("email")).strip().lower()
        except serializers.ValidationError:
            return Response({"email": ["بريد إلكتروني غير صالح."]}, status=400)
        if email == (self.patient.email or "").strip().lower():
            return Response({"email": ["هذا هو بريدك الحالي."]}, status=400)
        if PortalVerification.recent_count(
            purpose=PortalVerification.Purpose.EMAIL_CHANGE, key="email", key_value=email
        ) >= MAX_CODES_PER_ADDRESS:
            return Response({"detail": "محاولات كثيرة. حاول بعد قليل."}, status=429)
        channel = otp_channels.channel_for(self.tenant)
        _row, ticket, code = PortalVerification.issue(
            tenant=self.tenant, purpose=PortalVerification.Purpose.EMAIL_CHANGE,
            patient=self.patient, channel=channel.name, data={"email": email},
        )
        channel.send(
            tenant=self.tenant, branch=self.patient.branch, destination=email,
            code=code, purpose="email_change",
        )
        return Response({"ticket": ticket, "detail": EMAIL_CODE_SENT})


class EmailChangeVerifyView(PortalView):
    throttle_classes = [PortalLoginThrottle]

    def post(self, request, slug):
        ticket = str(request.data.get("ticket") or "").strip()
        code = str(request.data.get("code") or "").strip()
        # Looked up inside this patient's own rows: another patient's ticket is
        # simply not found.
        row = (
            PortalVerification.objects.filter(
                ticket_hash=hash_token(ticket), purpose=PortalVerification.Purpose.EMAIL_CHANGE,
                patient=self.patient,
            ).first()
            if ticket else None
        )
        with transaction.atomic():
            if row is None or not code or not row.verify(code):
                return Response({"detail": OTP_ERROR}, status=400)
            patient = self.patient
            patient.email = row.data["email"]
            patient.save(update_fields=["email", "updated_at"])
        return Response(profile_payload(patient))
