"""The patient portal API — `/api/portal/<clinic-slug>/…`.

How "a patient only ever sees their own data" is made true (docs/12 §3):

1. **Tenant.** `PortalView.dispatch` resolves the clinic from the URL and runs
   the whole request inside its `tenant_context`, so row-level security binds
   exactly as for that clinic's staff.
2. **Patient, at the queryset.** Every read starts from
   `Model.objects.filter(patient=<the signed-in patient>)`. No portal URL
   carries a patient identifier — "whose data" is answered only by the session.
   A record UUID is looked up inside that filtered queryset, so another
   patient's UUID is a 404 identical to one that never existed.
3. **Release.** Lab results and documents appear only once a clinician has
   released them; the diagnosis text only if the clinic has chosen to show it.

Every read of clinical data is written to the clinic's audit trail.
"""

from django.db import transaction
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from appointments.models import Appointment
from audit.models import AuditLog
from billing.models import Payment
from medical.models import (
    Allergy,
    LabResult,
    MedicalAttachment,
    Prescription,
    TreatmentPlan,
    TreatmentSession,
    Visit,
)
from tenants.context import tenant_context
from tenants.models import Tenant
from urllib.parse import quote

from .auth import (
    COOKIE,
    IsPortalPatient,
    PortalAuthentication,
    clear_session_cookie,
    enforce_csrf,
    set_session_cookie,
)
from .models import PatientAccount, PortalInvitation, PortalSession, hash_token

LOGIN_ERROR = "رقم الهاتف أو كلمة المرور غير صحيحة."
MAX_PENDING_REQUESTS = 3
LIST_CAP = 200


def normalize_phone(value):
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def me_payload(tenant, patient):
    from branches.printing import link_items

    return {
        "name": patient.name,
        "serial_number": patient.serial_number,
        "clinic": tenant.name,
        "show_diagnosis": tenant.portal_show_diagnosis,
        # The patient's own clinic's social and contact links (Print design).
        "links": link_items(getattr(patient.branch, "print_links", None)) if patient.branch_id else [],
    }


class PortalLoginThrottle(AnonRateThrottle):
    scope = "portal_login"


class PortalView(APIView):
    """Binds the clinic from the URL for the whole request, and fails closed."""

    authentication_classes = [PortalAuthentication]
    permission_classes = [IsPortalPatient]

    def dispatch(self, request, *args, **kwargs):
        tenant = Tenant.objects.filter(slug=kwargs.get("slug")).first()
        if tenant is None:
            return JsonResponse({"detail": "العيادة غير موجودة."}, status=404)
        if not tenant.is_usable:
            return JsonResponse(
                {"detail": "بوابة هذه العيادة متوقفة حالياً."}, status=403
            )
        self.tenant = tenant
        with tenant_context(tenant):
            return super().dispatch(request, *args, **kwargs)

    @property
    def patient(self):
        return self.request.user.patient

    def audit(self, what, model_name="", object_id=""):
        request = self.request
        AuditLog.objects.create(
            tenant=self.tenant,
            user=None,
            action="custom",
            model_name=model_name or "portal",
            object_id=str(object_id or self.patient.pk),
            description=f"[portal] patient {self.patient.serial_number} viewed {what}",
            ip_address=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT"),
        )


def signed_in(view, account, slug, payload, status_code=200):
    token = PortalSession.start(account)
    account.last_login = timezone.now()
    account.save(update_fields=["last_login"])
    response = Response(payload, status=status_code)
    set_session_cookie(response, slug, token)
    response["Cache-Control"] = "no-store"
    return response


# ------------------------------------------------------------------- auth


class AcceptInviteView(PortalView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [PortalLoginThrottle]

    def post(self, request, slug):
        enforce_csrf(request)
        token = str(request.data.get("token") or "").strip()
        password = str(request.data.get("password") or "")
        if len(password) < 8:
            return Response({"password": ["كلمة المرور ٨ أحرف على الأقل."]}, status=400)

        invitation = (
            PortalInvitation.objects.select_related("patient")
            .filter(token_hash=hash_token(token))
            .first()
            if token
            else None
        )
        if invitation is None or not invitation.is_usable:
            return Response(
                {"detail": "رابط الدعوة غير صالح أو انتهت صلاحيته. اطلب رابطاً جديداً من العيادة."},
                status=400,
            )

        with transaction.atomic():
            account, _ = PatientAccount.objects.get_or_create(
                patient=invitation.patient, defaults={"tenant": self.tenant}
            )
            account.set_password(password)
            account.is_active = True
            account.failed_logins = 0
            account.locked_until = None
            account.save()
            account.revoke_sessions()
            invitation.used_at = timezone.now()
            invitation.save(update_fields=["used_at"])
            return signed_in(self, account, slug, me_payload(self.tenant, invitation.patient))


class LoginView(PortalView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [PortalLoginThrottle]

    def post(self, request, slug):
        enforce_csrf(request)
        phone = normalize_phone(request.data.get("phone"))
        password = str(request.data.get("password") or "")
        if not phone or not password:
            return Response({"detail": LOGIN_ERROR}, status=400)

        # A household often shares one phone, so several accounts may match;
        # the password decides which one is signing in.
        matches = [
            account
            for account in PatientAccount.objects.select_related("patient").filter(is_active=True)
            if phone in (normalize_phone(account.patient.phone1), normalize_phone(account.patient.phone2))
        ]
        if not matches:
            return Response({"detail": LOGIN_ERROR}, status=400)
        if any(account.is_locked for account in matches):
            return Response(
                {"detail": "محاولات كثيرة. حاول مرة أخرى بعد ١٥ دقيقة."}, status=429
            )
        account = next((a for a in matches if a.check_password(password)), None)
        if account is None:
            for candidate in matches:
                candidate.register_failure()
            return Response({"detail": LOGIN_ERROR}, status=400)

        account.failed_logins = 0
        account.save(update_fields=["failed_logins"])
        return signed_in(self, account, slug, me_payload(self.tenant, account.patient))


class LogoutView(PortalView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request, slug):
        enforce_csrf(request)
        token = request.COOKIES.get(COOKIE)
        if token:
            PortalSession.objects.filter(
                token_hash=hash_token(token), revoked_at__isnull=True
            ).update(revoked_at=timezone.now())
        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_session_cookie(response, slug)
        return response


class MeView(PortalView):
    def get(self, request, slug):
        return Response(me_payload(self.tenant, self.patient))


# ------------------------------------------------------------------- data


class AppointmentsView(PortalView):
    def get(self, request, slug):
        rows = (
            Appointment.objects.filter(patient=self.patient)
            .select_related("doctor", "service")
            .order_by("-scheduled_date")[:LIST_CAP]
        )
        from platform_admin.clinic_pay import methods_for

        methods = methods_for(self.tenant, self.patient.branch)
        return Response([appointment_payload(a, can_pay=bool(methods)) for a in rows])

    def post(self, request, slug):
        """Request an appointment. Reception confirms it; nothing enters a
        doctor's schedule on the patient's say-so (decision D3)."""
        when = parse_datetime(str(request.data.get("scheduled_date") or ""))
        if when is None or when <= timezone.now():
            return Response({"scheduled_date": ["اختر موعداً في المستقبل."]}, status=400)
        pending = Appointment.objects.filter(patient=self.patient, status="requested").count()
        if pending >= MAX_PENDING_REQUESTS:
            return Response(
                {"detail": "لديك طلبات مواعيد لم تُؤكَّد بعد. انتظر رد العيادة."}, status=400
            )
        notes = str(request.data.get("notes") or "").strip()[:1000]
        # Atomic, so a failure after the INSERT — in a save signal, say —
        # rolls the row back instead of leaving a request the patient was told
        # had failed. An audit crash once did exactly that.
        with transaction.atomic():
            appointment = Appointment.objects.create(
                tenant=self.tenant,
                patient=self.patient,
                branch=self.patient.branch,
                status="requested",
                scheduled_date=when,
                price=0,
                notes=f"[طلب من بوابة المرضى] {notes}".strip(),
            )
        return Response(appointment_payload(appointment), status=201)


def appointment_payload(a, can_pay=False):
    from platform_admin.clinic_pay import due

    owed = due(a)
    return {
        "due": str(owed),
        "can_pay_online": can_pay and owed > 0,
        "uuid": str(a.uuid),
        "serial_number": a.serial_number,
        "scheduled_date": a.scheduled_date,
        "status": a.status,
        "status_label": a.get_status_display(),
        "doctor_name": getattr(a.doctor, "name", None),
        "service_name": getattr(a.service, "name", None),
    }


class PayOptionsView(PortalView):
    """The gateways this clinic takes online payments through — its own keys,
    set in the developer portal; empty when it has none."""

    def get(self, request, slug):
        from platform_admin.clinic_pay import methods_for

        return Response({"methods": methods_for(self.tenant, self.patient.branch)})


class AppointmentPayView(PortalView):
    """Start paying a booking online; returns where to send the browser."""

    def post(self, request, slug, uuid):
        from platform_admin import clinic_pay
        from platform_admin.gateways import GatewayError

        appointment = Appointment.objects.filter(uuid=uuid, patient=self.patient).select_related("branch").first()
        if appointment is None:
            return Response({"detail": "الحجز غير موجود."}, status=404)
        method = request.data.get("method")
        payer = {
            "name": self.patient.name,
            "email": getattr(self.patient, "email", "") or "",
            "phone": str(request.data.get("phone") or getattr(self.patient, "phone1", "") or "").strip(),
            "id": str(self.patient.uuid),
            "description": f"حجز {appointment.serial_number}",
        }
        try:
            result = clinic_pay.start(
                self.tenant, appointment, method, payer=payer,
                return_url=request.build_absolute_uri(f"/api/pay/{method}/callback/"),
            )
        except GatewayError as error:
            return Response({"detail": str(error)}, status=400)
        self.audit(f"online payment start {result['reference']}", model_name="Appointment", object_id=appointment.pk)
        return Response(result)


class VisitsView(PortalView):
    def get(self, request, slug):
        show = self.tenant.portal_show_diagnosis
        rows = (
            Visit.objects.filter(patient=self.patient)
            .select_related("doctor")
            .order_by("-visit_date")[:LIST_CAP]
        )
        self.audit("visits")
        return Response([
            {
                "uuid": str(v.uuid),
                "visit_date": v.visit_date,
                "doctor_name": getattr(v.doctor, "name", None),
                "follow_up_date": v.follow_up_date,
                # Only if the clinic has chosen to share it (decision D2).
                # Examination notes never leave the clinic.
                "diagnosis": v.diagnosis if show else None,
            }
            for v in rows
        ])


def prescription_payload(p):
    return {
        "uuid": str(p.uuid),
        "serial_number": p.serial_number,
        "issued_at": p.issued_at,
        "doctor_name": getattr(p.doctor, "name", None),
        "notes": p.notes,
        "items": [
            {
                "medication": item.medication,
                "dosage": item.dosage,
                "frequency": item.frequency,
                "duration": item.duration,
                "instructions": item.instructions,
            }
            for item in p.items.all()
        ],
    }


class PrescriptionsView(PortalView):
    def get(self, request, slug):
        rows = (
            Prescription.objects.filter(patient=self.patient)
            .select_related("doctor")
            .prefetch_related("items")
            .order_by("-issued_at")[:LIST_CAP]
        )
        self.audit("prescriptions")
        return Response([prescription_payload(p) for p in rows])


class PrescriptionDetailView(PortalView):
    def get(self, request, slug, uuid):
        prescription = get_object_or_404(
            Prescription.objects.filter(patient=self.patient).prefetch_related("items"),
            uuid=uuid,
        )
        self.audit(f"prescription {prescription.serial_number}", "Prescription", prescription.pk)
        return Response(prescription_payload(prescription))


class LabResultsView(PortalView):
    def get(self, request, slug):
        rows = LabResult.objects.filter(
            patient=self.patient, released_to_patient=True
        ).order_by("-ordered_at")[:LIST_CAP]
        self.audit("released lab results")
        return Response([
            {
                "uuid": str(r.uuid),
                "test_name": r.test_name,
                "value": r.value,
                "unit": r.unit,
                "reference_range": r.reference_range,
                "flag": r.flag,
                "flag_label": r.get_flag_display(),
                "resulted_at": r.resulted_at,
                "lab_name": r.lab_name,
            }
            for r in rows
        ])


class AttachmentsView(PortalView):
    def get(self, request, slug):
        rows = MedicalAttachment.objects.filter(
            patient=self.patient, released_to_patient=True
        ).order_by("-created_at")[:LIST_CAP]
        return Response([
            {
                "uuid": str(a.uuid),
                "title": a.title,
                "category_label": a.get_category_display(),
                "size_bytes": a.size_bytes,
                "created_at": a.created_at,
                "original_filename": a.original_filename,
            }
            for a in rows
        ])


class AttachmentDownloadView(PortalView):
    def get(self, request, slug, uuid):
        attachment = get_object_or_404(
            MedicalAttachment.objects.filter(patient=self.patient, released_to_patient=True),
            uuid=uuid,
        )
        if not attachment.file:
            raise Http404
        self.audit(f"document {attachment.serial_number}", "MedicalAttachment", attachment.pk)
        response = FileResponse(
            attachment.file.open("rb"),
            content_type=attachment.content_type or "application/octet-stream",
        )
        name = attachment.original_filename or "document"
        response["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(name)}"
        response["X-Content-Type-Options"] = "nosniff"
        return response


class PaymentsView(PortalView):
    def get(self, request, slug):
        rows = (
            Payment.objects.filter(patient=self.patient)
            .select_related("method")
            .order_by("-date")[:LIST_CAP]
        )
        return Response([
            {
                "uuid": str(p.uuid),
                "receipt_number": p.receipt_number,
                "amount": p.amount,
                "date": p.date,
                "method_name": getattr(p.method, "name", None),
            }
            for p in rows
        ])


class TreatmentPlansView(PortalView):
    def get(self, request, slug):
        rows = TreatmentPlan.objects.filter(patient=self.patient).order_by("-start_date")
        return Response([
            {
                "uuid": str(plan.uuid),
                "title": plan.title,
                "planned_sessions": plan.planned_sessions,
                "completed_sessions": plan.sessions.filter(
                    status=TreatmentSession.Status.COMPLETED
                ).count(),
                "status_label": plan.get_status_display(),
                "start_date": plan.start_date,
            }
            for plan in rows
        ])


class AllergiesView(PortalView):
    def get(self, request, slug):
        return Response([
            {
                "substance": a.substance,
                "reaction": a.reaction,
                "severity_label": a.get_severity_display(),
            }
            for a in Allergy.objects.filter(patient=self.patient)
        ])
