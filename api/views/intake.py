"""First-visit intake from the front desk, and the clinical view of it.

Registration is a front-desk act (Reception, clinic Admin, Owner). Reading the
medical history back is clinical: Reception may *enter* it with the patient in
front of them, but it is served afterwards only to clinical roles, like every
other clinical record.
"""

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.roles import is_front_desk, scope_queryset_to_user, sees_all_branches
from api.permissions import CanViewClinical, IsClinicMember
from api.serializers.intake import (
    IntakeRegistrationSerializer,
    MedicalHistorySerializer,
    PatientConditionSerializer,
    PatientIntakeSerializer,
)
from api.viewsets import ReadOnlyClinicViewSet
from medical.models import PatientCondition, PatientIntake, PatientMedicalProfile
from patients.intake import (
    PROFILE_FIELDS,
    RegistrationError,
    check_doctor_branch,
    confirmed_patients,
    duplicate_candidates,
    register_patient,
)
from patients.models import Patient
from subscriptions.entitlements import LimitReached, check_limit
from subscriptions.usage import limit_message
from tenants.context import get_current_tenant


class IsFrontDesk(IsClinicMember):
    message = "التسجيل مقصور على الاستقبال والإدارة."

    def has_permission(self, request, view):
        return super().has_permission(request, view) and is_front_desk(request.user)


def duplicate_payload(user, candidates):
    """Matches the caller may see, in full; matches in other clinics, as a
    count only — the front desk must learn that the person may already be a
    patient of the group without being shown another clinic's patient."""
    visible = scope_queryset_to_user(candidates, user)
    rows = [
        {"uuid": str(p.uuid), "name": p.name, "serial_number": p.serial_number, "phone1": p.phone1}
        for p in visible[:10]
    ]
    return {"duplicates": rows, "other_clinics": candidates.count() - visible.count()}


class DuplicateCheckView(APIView):
    """`GET /api/intake/duplicates/?phone=&whatsapp=&national_id=` — asked by
    the wizard as soon as step 1 is filled, so a duplicate is caught before
    the patient has answered five screens of questions."""

    permission_classes = [IsFrontDesk]

    def get(self, request):
        params = request.query_params
        candidates = duplicate_candidates(
            phone=params.get("phone", ""), whatsapp=params.get("whatsapp", ""),
            national_id=params.get("national_id", ""),
        )
        return Response(duplicate_payload(request.user, candidates))


class IntakeRegistrationView(APIView):
    """`POST /api/intake/register/` — the whole wizard, in one transaction."""

    permission_classes = [IsFrontDesk]

    def post(self, request):
        serializer = IntakeRegistrationSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        tenant = get_current_tenant()
        personal = dict(data["personal"])
        user = request.user

        # Which clinic: the Owner chooses; everyone else registers into their own.
        branch = personal.get("branch") or user.branch
        if branch is None:
            return Response({"personal": {"branch": ["اختر العيادة."]}}, status=400)
        if not sees_all_branches(user) and branch.pk != user.branch_id:
            return Response({"personal": {"branch": ["يمكنك التسجيل في عيادتك فقط."]}}, status=400)
        personal["branch"] = branch

        try:
            check_doctor_branch(data["visit"].get("requested_doctor"), branch)
        except RegistrationError as error:
            return Response({"visit": {"requested_doctor": [str(error)]}}, status=400)

        candidates = duplicate_candidates(
            phone=personal.get("phone1", ""), whatsapp=personal.get("whatsapp", ""),
            national_id=personal.get("national_id", ""),
        )
        if candidates.exists() and not data["confirm_new"]:
            return Response(
                {"detail": "قد يكون هذا المريض مسجلاً بالفعل.", **duplicate_payload(user, candidates)},
                status=status.HTTP_409_CONFLICT,
            )

        try:
            check_limit(tenant, "max_patients", confirmed_patients().count())
        except LimitReached as reached:
            return Response({"detail": limit_message(reached)}, status=403)

        patient, intake = register_patient(
            tenant=tenant, personal=personal, visit=data["visit"],
            history=data.get("history"), referral=data.get("referral"),
            consent=data["consent"], actor=user,
        )
        # Deliberately minimal: Reception entered the history, but is not
        # shown it back — clinical data is served to clinical roles only.
        return Response(
            {"patient": {"uuid": str(patient.uuid), "serial_number": patient.serial_number, "name": patient.name},
             "intake": str(intake.uuid)},
            status=status.HTTP_201_CREATED,
        )


class PatientHistoryView(APIView):
    """`GET/PUT /api/patients/<uuid>/history/` — the reported history, for
    clinicians. Scoped to the caller's clinics like the patient itself."""

    permission_classes = [CanViewClinical]

    def patient(self, request, uuid):
        return get_object_or_404(scope_queryset_to_user(Patient.objects.all(), request.user), uuid=uuid)

    def payload(self, patient):
        profile = PatientMedicalProfile.objects.filter(patient=patient).first()
        return {
            **{field: getattr(profile, field) if profile else "" for field in PROFILE_FIELDS},
            "conditions_reviewed": bool(profile and profile.conditions_reviewed),
            "conditions": PatientConditionSerializer(
                PatientCondition.objects.filter(patient=patient).order_by("condition"), many=True
            ).data,
            "updated_at": profile.updated_at if profile else None,
        }

    def get(self, request, uuid):
        return Response(self.payload(self.patient(request, uuid)))

    def put(self, request, uuid):
        patient = self.patient(request, uuid)
        serializer = MedicalHistorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        conditions = data.pop("conditions", [])
        tenant = get_current_tenant()
        with transaction.atomic():
            profile, _ = PatientMedicalProfile.objects.get_or_create(
                patient=patient, defaults={"tenant": tenant}
            )
            for field, value in data.items():
                setattr(profile, field, value)
            profile.updated_by = request.user
            profile.save()
            PatientCondition.objects.filter(patient=patient).delete()
            for condition in conditions:
                PatientCondition.objects.create(
                    tenant=tenant, patient=patient, recorded_by=request.user, **condition
                )
        return Response(self.payload(patient))


class PatientIntakeViewSet(ReadOnlyClinicViewSet):
    """Why patients came, as they told it. Clinical, and per clinic."""

    queryset = PatientIntake.objects.all()
    serializer_class = PatientIntakeSerializer
    permission_classes = [CanViewClinical]
    ordering = ["-created_at"]

    def filter_tenant_queryset(self, queryset):
        queryset = queryset.select_related("patient", "branch", "specialization", "requested_doctor")
        patient = self.request.query_params.get("patient")
        return queryset.filter(patient__uuid=patient) if patient else queryset
