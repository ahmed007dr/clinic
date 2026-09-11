"""Patients."""

from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from api.permissions import DeleteRequiresAdmin, IsClinicMember, can_view_clinical
from api.serializers.patients import PatientListSerializer, PatientSerializer
from api.viewsets import ClinicViewSet
from billing.access import restrict_payments
from patients.models import Patient
from django.utils import timezone
from portal.models import PatientAccount, PortalInvitation
from tenants.context import get_current_tenant


class PatientViewSet(ClinicViewSet):
    queryset = Patient.objects.all()
    serializer_class = PatientSerializer
    permission_classes = [IsClinicMember, DeleteRequiresAdmin]
    plan_limit = "max_patients"
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["name", "serial_number", "phone1", "phone2", "national_id"]
    ordering_fields = ["name", "created_at", "serial_number"]
    ordering = ["-created_at"]

    def plan_limit_count(self):
        from patients.intake import confirmed_patients

        return confirmed_patients().count()

    def filter_tenant_queryset(self, queryset):
        queryset = queryset.select_related("branch")
        params = self.request.query_params
        if params.get("needs_review") == "1":
            queryset = queryset.filter(needs_review=True)
        elif self.action == "list":
            # A self-registration is not a patient until the desk confirms it:
            # it waits on the review screen, not in the patient list.
            queryset = queryset.filter(needs_review=False)
        if params.get("branch"):
            queryset = queryset.filter(branch__uuid=params["branch"])
        if params.get("referral_source"):
            queryset = queryset.filter(referral_source=params["referral_source"])
        return queryset

    def get_serializer_class(self):
        # The list screen renders six columns; sending the full record for
        # every row turns a page of results into a bulk export of contact
        # details and national IDs.
        if self.action == "list":
            return PatientListSerializer
        return PatientSerializer

    @action(detail=True, methods=["get"], url_path="timeline")
    def timeline(self, request, uuid=None):
        """Everything that happened to this patient, in one ordered list.

        The gap §19 has been open on since the beginning: the data existed but
        was only ever shown as separate tables per record type, so nobody could
        see a patient's history as a history. Assembled server-side because the
        ordering is across six models and doing it in the client means six
        requests and a merge that goes wrong the first time two things share a
        timestamp.

        Clinical entries are included only for clinical roles, and payments
        only as far as billing.access allows — the same rules as everywhere,
        applied to a merged list.
        """
        patient = self.get_object()
        entries = []

        def add(kind, when, title, detail=None, uuid_value=None, extra=None):
            if when is None:
                return
            entries.append(
                {
                    "kind": kind,
                    "at": when,
                    "title": title,
                    "detail": detail or "",
                    "uuid": str(uuid_value) if uuid_value else None,
                    **(extra or {}),
                }
            )

        for appointment in patient.appointment_set.select_related(
            "doctor", "service"
        ):
            add(
                "appointment",
                appointment.scheduled_date,
                appointment.service.name if appointment.service else "موعد",
                appointment.get_status_display(),
                appointment.uuid,
                {"doctor": getattr(appointment.doctor, "name", None)},
            )

        # The same money rule as the payments list, or the timeline becomes the
        # way round it: one patient at a time, every amount on every date.
        payments = restrict_payments(patient.payment_set.all(), request.user)
        for payment in payments.select_related("method"):
            add(
                "payment",
                payment.date,
                f"دفعة {payment.amount}",
                getattr(payment.method, "name", ""),
                payment.uuid,
            )

        if can_view_clinical(request.user):
            for visit in patient.visits.select_related("doctor"):
                add(
                    "visit",
                    visit.visit_date,
                    visit.chief_complaint or "زيارة",
                    visit.diagnosis,
                    visit.uuid,
                    {"doctor": getattr(visit.doctor, "name", None)},
                )
            for prescription in patient.prescriptions.all():
                add(
                    "prescription",
                    prescription.issued_at,
                    "روشتة",
                    prescription.notes,
                    prescription.uuid,
                )
            for procedure in patient.procedures.all():
                add(
                    "procedure",
                    procedure.performed_at,
                    procedure.name,
                    procedure.outcome,
                    procedure.uuid,
                )
            for lab in patient.lab_results.all():
                add(
                    "lab",
                    lab.resulted_at or lab.ordered_at,
                    lab.test_name,
                    f"{lab.value} {lab.unit}".strip(),
                    lab.uuid,
                    {"flag": lab.flag},
                )
            for session in patient.treatment_sessions.select_related("plan"):
                add(
                    "session",
                    session.performed_at or session.scheduled_date,
                    f"جلسة {session.sequence} — {session.plan.title}",
                    session.get_status_display(),
                    session.uuid,
                )

        entries.sort(key=lambda entry: entry["at"], reverse=True)
        return Response({"patient": patient.name, "entries": entries})

    # ------------------------------------------------------ patient portal

    @action(detail=True, methods=["get"], url_path="portal")
    def portal_status(self, request, uuid=None):
        patient = self.get_object()
        account = PatientAccount.objects.filter(patient=patient).first()
        invite = (
            PortalInvitation.objects.filter(
                patient=patient, used_at__isnull=True, expires_at__gt=timezone.now()
            )
            .order_by("-created_at")
            .first()
        )
        return Response({
            "has_account": account is not None,
            "is_active": bool(account and account.is_active),
            "last_login": account.last_login if account else None,
            "invite_expires_at": invite.expires_at if invite else None,
        })

    @action(detail=True, methods=["post"], url_path="portal-invite")
    def portal_invite(self, request, uuid=None):
        """A single-use link for the patient to set a portal password.

        The token travels in the URL *fragment* (after `#`), which browsers
        never send to a server — so it cannot end up in an access log. It is
        shown to staff once and stored only as a hash.
        """
        patient = self.get_object()
        if not patient.phone1:
            return Response(
                {"detail": "سجّل رقم هاتف المريض أولاً — الدخول إلى البوابة يتم برقم الهاتف."},
                status=400,
            )
        invitation, token = PortalInvitation.issue(patient, created_by=request.user)
        slug = get_current_tenant().slug
        url = request.build_absolute_uri(f"/app/portal/{slug}/invite") + f"#{token}"
        response = Response({"url": url, "expires_at": invitation.expires_at})
        response["Cache-Control"] = "no-store"
        return response

    @action(detail=True, methods=["post"], url_path="portal-revoke")
    def portal_revoke(self, request, uuid=None):
        patient = self.get_object()
        account = PatientAccount.objects.filter(patient=patient).first()
        if account:
            account.is_active = False
            account.save(update_fields=["is_active"])
            account.revoke_sessions()
        return Response(status=204)

    # ------------------------------------------------ self-registration review

    def _front_desk(self, request):
        from rest_framework.exceptions import PermissionDenied

        from accounts.roles import is_front_desk

        if not is_front_desk(request.user):
            raise PermissionDenied("مراجعة التسجيلات مقصورة على الاستقبال والإدارة.")

    @action(detail=True, methods=["get"], url_path="review")
    def review(self, request, uuid=None):
        """A pending self-registration and the patients it might duplicate."""
        from api.views.intake import duplicate_payload
        from patients.intake import duplicate_candidates

        self._front_desk(request)
        patient = self.get_object()
        candidates = duplicate_candidates(
            phone=patient.phone1 or "", whatsapp=patient.whatsapp,
            national_id=patient.national_id or "", exclude_pk=patient.pk,
        ).filter(needs_review=False)
        return Response({"patient": PatientSerializer(patient, context={"request": request}).data,
                         **duplicate_payload(request.user, candidates)})

    @action(detail=True, methods=["post"], url_path="confirm-registration")
    def confirm_registration(self, request, uuid=None):
        from patients.intake import confirm_registration
        from subscriptions.entitlements import LimitReached
        from subscriptions.usage import limit_message

        self._front_desk(request)
        try:
            patient = confirm_registration(self.get_object(), get_current_tenant())
        except LimitReached as reached:
            return Response({"detail": limit_message(reached)}, status=403)
        return Response(PatientSerializer(patient, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="merge-into")
    def merge_into(self, request, uuid=None):
        """Fold this self-registration into an existing patient (`target`)."""
        from patients.intake import RegistrationError, merge_registration

        self._front_desk(request)
        source = self.get_object()
        # The target is looked up through the same scoped queryset: a clinic's
        # desk cannot merge into another clinic's patient.
        target = self.get_queryset().filter(uuid=request.data.get("target"), needs_review=False).first()
        if target is None:
            return Response({"target": ["اختر المريض الذي تريد الدمج فيه."]}, status=400)
        try:
            merged = merge_registration(source, target)
        except RegistrationError as error:
            return Response({"detail": str(error)}, status=400)
        return Response(PatientSerializer(merged, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="reject-registration")
    def reject_registration(self, request, uuid=None):
        from patients.intake import RegistrationError, reject_registration

        self._front_desk(request)
        try:
            reject_registration(self.get_object())
        except RegistrationError as error:
            return Response({"detail": str(error)}, status=400)
        return Response(status=204)
