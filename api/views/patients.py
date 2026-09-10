"""Patients."""

from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from api.permissions import IsClinicMember, can_view_clinical
from api.serializers.patients import PatientListSerializer, PatientSerializer
from api.viewsets import ClinicViewSet
from patients.models import Patient


class PatientViewSet(ClinicViewSet):
    queryset = Patient.objects.all()
    serializer_class = PatientSerializer
    permission_classes = [IsClinicMember]
    plan_limit = "max_patients"
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["name", "serial_number", "phone1", "phone2", "national_id"]
    ordering_fields = ["name", "created_at", "serial_number"]
    ordering = ["-created_at"]

    def filter_tenant_queryset(self, queryset):
        return queryset.select_related("branch")

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

        Clinical entries are included only for clinical roles. Reception sees
        the appointments and payments it created and nothing else — the same
        rule as everywhere, applied to a merged list.
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

        for payment in patient.payment_set.select_related("method"):
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
