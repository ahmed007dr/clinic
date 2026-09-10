"""Clinical endpoints. Every one of them is gated by `CanViewClinical`."""

from django.http import FileResponse, Http404
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from django.utils import timezone
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from rest_framework.exceptions import PermissionDenied

from api.permissions import CanViewClinical
from subscriptions.entitlements import LimitReached
from subscriptions.usage import check_storage, limit_message
from tenants.context import get_current_tenant
from api.serializers.clinical import (
    AllergySerializer,
    LabResultSerializer,
    MedicalAttachmentSerializer,
    PrescriptionSerializer,
    ProcedureSerializer,
    TreatmentPlanSerializer,
    TreatmentSessionSerializer,
    VisitSerializer,
)
from api.viewsets import ClinicViewSet
from medical.models import (
    Allergy,
    LabResult,
    MedicalAttachment,
    Procedure,
    Prescription,
    TreatmentPlan,
    TreatmentSession,
    Visit,
)


class ClinicalViewSet(ClinicViewSet):
    """Shared gate. Subclasses declare data, never policy."""

    permission_classes = [CanViewClinical]
    created_by_field = "created_by"

    def patient_filtered(self, queryset):
        patient = self.request.query_params.get("patient")
        return queryset.filter(patient__uuid=patient) if patient else queryset


class ReleaseToPatientMixin:
    """`POST …/release/ {released}` — show or hide a record in the patient
    portal. A clinical act with a named actor, so it is its own endpoint and
    not a field any edit can flip."""

    @action(detail=True, methods=["post"], url_path="release")
    def release(self, request, uuid=None):
        record = self.get_object()
        released = request.data.get("released", True) is True
        record.released_to_patient = released
        record.released_at = timezone.now() if released else None
        record.released_by = request.user if released else None
        record.save(update_fields=["released_to_patient", "released_at", "released_by"])
        return Response(self.get_serializer(record).data)


class VisitViewSet(ClinicalViewSet):
    queryset = Visit.objects.all()
    serializer_class = VisitSerializer
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = [
        "serial_number", "patient__name", "chief_complaint", "diagnosis",
    ]
    ordering_fields = ["visit_date", "created_at"]
    ordering = ["-visit_date"]

    def filter_tenant_queryset(self, queryset):
        return self.patient_filtered(
            queryset.select_related("patient", "doctor", "branch")
        )


class PrescriptionViewSet(ClinicalViewSet):
    queryset = Prescription.objects.all()
    serializer_class = PrescriptionSerializer
    # Its own branch lives on the visit that issued it — mirrors
    # medical/views.py rather than inventing a second rule.
    branch_field = "visit__branch"
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["serial_number", "patient__name", "items__medication"]
    ordering = ["-issued_at"]

    def filter_tenant_queryset(self, queryset):
        return self.patient_filtered(
            queryset.select_related("patient", "doctor", "visit").prefetch_related(
                "items"
            )
        ).distinct()


class TreatmentPlanViewSet(ClinicalViewSet):
    queryset = TreatmentPlan.objects.all()
    serializer_class = TreatmentPlanSerializer
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["serial_number", "title", "patient__name"]
    ordering = ["-start_date"]

    def filter_tenant_queryset(self, queryset):
        queryset = queryset.select_related("patient", "doctor", "service", "branch")
        status = self.request.query_params.get("status")
        if status:
            queryset = queryset.filter(status=status)
        return self.patient_filtered(queryset)


class TreatmentSessionViewSet(ClinicalViewSet):
    queryset = TreatmentSession.objects.all()
    serializer_class = TreatmentSessionSerializer
    branch_field = "plan__branch"
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["patient__name", "plan__title"]
    ordering = ["-scheduled_date"]

    def filter_tenant_queryset(self, queryset):
        queryset = queryset.select_related("plan", "patient", "doctor")
        plan = self.request.query_params.get("plan")
        if plan:
            queryset = queryset.filter(plan__uuid=plan)
        status = self.request.query_params.get("status")
        if status:
            queryset = queryset.filter(status=status)
        return self.patient_filtered(queryset)


class ProcedureViewSet(ClinicalViewSet):
    queryset = Procedure.objects.all()
    serializer_class = ProcedureSerializer
    branch_field = "visit__branch"
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["serial_number", "name", "patient__name"]
    ordering = ["-performed_at"]

    def filter_tenant_queryset(self, queryset):
        return self.patient_filtered(
            queryset.select_related("patient", "doctor", "visit", "service")
        )


class LabResultViewSet(ReleaseToPatientMixin, ClinicalViewSet):
    queryset = LabResult.objects.all()
    serializer_class = LabResultSerializer
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["serial_number", "test_name", "patient__name", "lab_name"]
    ordering = ["-ordered_at"]

    def filter_tenant_queryset(self, queryset):
        queryset = queryset.select_related(
            "patient", "ordered_by", "branch", "acknowledged_by"
        )
        status = self.request.query_params.get("status")
        if status:
            queryset = queryset.filter(status=status)
        flag = self.request.query_params.get("flag")
        if flag:
            queryset = queryset.filter(flag=flag)
        if self.request.query_params.get("unacknowledged") == "1":
            # The same definition the dashboard counts: results that need a
            # human. A normal result nobody has clicked is not waiting on
            # anyone, and including it made the dashboard say "1" while the
            # list it links to showed five.
            queryset = queryset.filter(acknowledged_at__isnull=True).exclude(
                flag=LabResult.Flag.NORMAL
            )
        return self.patient_filtered(queryset)

    @action(detail=True, methods=["post"], url_path="acknowledge")
    def acknowledge(self, request, uuid=None):
        """A named clinician says they have seen this result.

        Its own endpoint, and it delegates to `LabResult.acknowledge` rather
        than setting the two fields here: an abnormal result that nobody
        acknowledges is the thing this field exists to make visible, so who
        acknowledged it and when must not be settable as part of an ordinary
        edit.
        """
        result = self.get_object()
        if result.acknowledge(request.user):
            return Response(self.get_serializer(result).data)
        return Response(
            {"detail": "تم الاطلاع على هذه النتيجة بالفعل."}, status=400
        )


class MedicalAttachmentViewSet(ReleaseToPatientMixin, ClinicalViewSet):
    queryset = MedicalAttachment.objects.all()
    serializer_class = MedicalAttachmentSerializer
    created_by_field = "uploaded_by"
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["serial_number", "title", "patient__name", "original_filename"]
    ordering = ["-created_at"]

    def perform_create(self, serializer):
        # Before the file is written — refusing afterwards leaves it on disk.
        upload = serializer.validated_data.get("file")
        try:
            check_storage(get_current_tenant(), getattr(upload, "size", 0) or 0)
        except LimitReached as reached:
            raise PermissionDenied(limit_message(reached))
        super().perform_create(serializer)

    def filter_tenant_queryset(self, queryset):
        queryset = queryset.select_related("patient", "visit", "lab_result")
        category = self.request.query_params.get("category")
        if category:
            queryset = queryset.filter(category=category)
        return self.patient_filtered(queryset)

    @action(detail=True, methods=["get"], url_path="download")
    def download(self, request, uuid=None):
        """Stream the file through the application.

        The storage deliberately has no URL: `PrivateAttachmentStorage.url()`
        raises, and the files live outside the web root, so this view is the
        only way to read one. That is what makes every permission check above
        apply to the file itself and not merely to the record describing it —
        a link the web server can serve has bypassed all of them.
        """
        attachment = self.get_object()
        if not attachment.file:
            raise Http404
        response = FileResponse(
            attachment.file.open("rb"),
            content_type=attachment.content_type or "application/octet-stream",
        )
        filename = attachment.original_filename or "attachment"
        # RFC 5987, because the original name is very often Arabic.
        from urllib.parse import quote

        response["Content-Disposition"] = (
            f"attachment; filename*=UTF-8''{quote(filename)}"
        )
        response["X-Content-Type-Options"] = "nosniff"
        return response


class AllergyViewSet(ClinicalViewSet):
    """Allergies. Scoped through the patient's branch — the record has none of
    its own, and a doctor must not read another branch's patients by listing
    their allergies."""

    queryset = Allergy.objects.all()
    serializer_class = AllergySerializer
    branch_field = "patient__branch"
    created_by_field = "recorded_by"
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["substance", "patient__name"]
    ordering = ["substance"]
    # The whole list for one patient fits on a banner; paging it would hide
    # the allergy that matters on page two.
    pagination_class = None

    def filter_tenant_queryset(self, queryset):
        return self.patient_filtered(queryset.select_related("patient", "recorded_by"))
