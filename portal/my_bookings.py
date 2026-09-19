"""A patient managing their own bookings — details, cancel, ask to reschedule (docs/15, Phase 6).

    GET  appointments/<uuid>/              the booking, what is owed, what was paid, and what can be done
    POST appointments/<uuid>/cancel/       cancel it, if the clinic's rules allow
    POST appointments/<uuid>/reschedule/   `{slot, notes}` — ask for another time; the clinic agrees it by phone

Every lookup starts from the signed-in patient's own bookings, so another
patient's uuid is a 404 identical to one that never existed.

**The clinic's rules** (nothing here is the patient's to decide):

* Only a booking still ahead can be changed: `requested`, `waiting` or `quick`.
  Once the patient has been called in, has been seen, or the booking is closed,
  it is the clinic's alone.
* A request the clinic has not confirmed can always be withdrawn. A confirmed one
  only up to `Branch.online_cancel_notice_hours` before it starts (24 unless the
  clinic changes it; 0 = any time before).
* A booking with money paid on it is not cancelled from here — refunds are the
  clinic's, and a cancellation would leave a payment and a doctor's share
  hanging from a booking that no longer exists.
* Asking to reschedule moves nothing. It records the time the patient would like
  (which must be one the doctor actually offers) for the clinic to settle, and
  the clinic's own edit of the booking's time clears it.
"""

from datetime import timedelta

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.response import Response

from appointments.availability import is_offered
from appointments.models import Appointment
from billing.collect import amount_paid
from services.catalog import resolve_offering

from .booking import _slot
from .views import PortalView, appointment_payload

CHANGEABLE = ("requested", "waiting", "quick")


def notice_of(appointment):
    """Hours a confirmed booking must still be ahead of, at its clinic."""
    return getattr(appointment.branch, "online_cancel_notice_hours", 24) if appointment.branch_id else 24


def change_problem(appointment, now=None):
    """Why this booking cannot be cancelled or moved by the patient, or None."""
    now = now or timezone.now()
    if appointment.status not in CHANGEABLE:
        return "لا يمكن تعديل هذا الحجز في حالته الحالية. تواصل مع العيادة."
    if appointment.status != "requested":
        hours = notice_of(appointment)
        if appointment.scheduled_date - now < timedelta(hours=hours):
            if appointment.scheduled_date < now:
                return "انتهى موعد هذا الحجز."
            return f"لا يمكن التعديل قبل الموعد بأقل من {hours} ساعة. تواصل مع العيادة."
    return None


def cancel_problem(appointment, now=None):
    problem = change_problem(appointment, now)
    if problem:
        return problem
    if amount_paid(appointment) > 0:
        return "عليه مبلغ مدفوع؛ تواصل مع العيادة لإلغائه واسترداد المبلغ."
    return None


class _MyBooking(PortalView):
    def booking(self, uuid):
        return get_object_or_404(
            Appointment.objects.filter(patient=self.patient).select_related("branch", "doctor", "service"),
            uuid=uuid,
        )


class AppointmentDetailView(_MyBooking):
    def get(self, request, slug, uuid):
        from billing.models import Payment

        appointment = self.booking(uuid)
        payload = appointment_payload(appointment)
        payload["payments"] = [
            {
                "receipt_number": p.receipt_number, "amount": str(p.amount), "date": p.date,
                "method_name": getattr(p.method, "name", None),
            }
            for p in Payment.objects.filter(appointment=appointment).select_related("method").order_by("date")
        ]
        return Response(payload)


class AppointmentCancelView(_MyBooking):
    @transaction.atomic
    def post(self, request, slug, uuid):
        appointment = self.booking(uuid)
        problem = cancel_problem(appointment)
        if problem:
            return Response({"detail": problem}, status=400)
        appointment.status = "cancelled"
        appointment.reschedule_requested_for = None
        appointment.reschedule_note = ""
        appointment.notes = f"{appointment.notes or ''}\n[ألغاه المريض من البوابة]".strip()
        appointment.save(update_fields=["status", "reschedule_requested_for", "reschedule_note", "notes"])
        from notifications import booking as told

        transaction.on_commit(lambda: told.patient_cancelled(appointment))
        return Response(appointment_payload(appointment))


class AppointmentRescheduleView(_MyBooking):
    @transaction.atomic
    def post(self, request, slug, uuid):
        appointment = self.booking(uuid)
        problem = change_problem(appointment)
        if problem:
            return Response({"detail": problem}, status=400)
        when = _slot(request.data.get("slot"))
        if when is None or when <= timezone.now():
            return Response({"slot": ["اختر موعدًا قادمًا من الأوقات المتاحة."]}, status=400)
        if when == appointment.scheduled_date:
            return Response({"slot": ["هذا هو موعد حجزك الحالي."]}, status=400)

        # A booking made from the catalogue can only move to a time its doctor is
        # really offered; an older one (no doctor or service) just to a future time.
        if appointment.doctor_id and appointment.service_id and appointment.branch_id:
            offer = resolve_offering(appointment.branch, appointment.doctor, appointment.service)
            if offer is None or not is_offered(offer, when):
                return Response({"slot": ["هذا الوقت غير متاح. اختر وقتًا آخر."]}, status=409)

        appointment.reschedule_requested_for = when
        appointment.reschedule_note = str(request.data.get("notes") or "").strip()[:300]
        appointment.save(update_fields=["reschedule_requested_for", "reschedule_note"])
        from notifications import booking as told

        transaction.on_commit(lambda: told.patient_asked_to_move(appointment))
        return Response(appointment_payload(appointment))
