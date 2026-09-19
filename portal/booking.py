"""Booking from the catalogue: service → clinic → doctor → an offered time (docs/15, Phase 5).

`POST portal/<slug>/appointments/` with `{service, branch, doctor, slot, notes}`
(uuids and `slot` as "YYYY-MM-DD HH:MM"). Nothing the client says is trusted:

* the choice is re-resolved with `services.catalog.resolve_offering` — the same
  rule that produced the lists — so a clinic that does not offer the service, or
  a doctor who cannot deliver it there, is refused whatever the page showed;
* the time must be one of the times the doctor is actually offered
  (`appointments.availability.is_offered`), checked again here;
* a patient may book at a clinic other than their own only if the group allows it
  (`Tenant.portal_allow_other_branches`, docs/15 D10);
* the price is the contract's — the patient never sets one.

What is created depends on the clinic (docs/15, D3, D4). By default it is a
**request** (`requested`): it holds no time, and the clinic phones the customer
to settle the real one. A clinic that confirms website bookings at once
(`Branch.online_booking_confirms_at_once`) gets a `waiting` booking, created
under a lock on the doctor's row with the time re-checked inside it, so two
customers choosing the same time cannot both get it — the second is told (409).
"""

import uuid as uuid_module
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils.dateparse import parse_datetime
from rest_framework.response import Response

from appointments.availability import is_offered
from appointments.models import Appointment
from billing.pricing import quantity_problem, quantity_total
from branches.models import Branch
from employees.models import Employee
from services.catalog import resolve_offering
from services.models import Service

MAX_PENDING_REQUESTS = 3
NOT_BOOKABLE = "هذا الاختيار غير متاح للحجز. اختر من القائمة."
TAKEN = "هذا الوقت لم يعد متاحًا. اختر وقتًا آخر."
#: What reception sees first in the notes — and what marked portal bookings
#: before `Appointment.source` existed.
NOTE_PREFIX = "[طلب من بوابة المرضى]"


def _uuid(value):
    try:
        return uuid_module.UUID(str(value or ""))
    except ValueError:
        return None


def _slot(value):
    """`YYYY-MM-DD HH:MM` (or ISO) as naive clinic-local time, or None."""
    text = str(value or "").strip().replace("T", " ")
    try:
        # Well formatted but impossible ("2030-13-40 09:00") raises ValueError.
        parsed = parse_datetime(text) or parse_datetime(text + ":00")
        if parsed is None:
            parsed = datetime.strptime(text, "%Y-%m-%d %H:%M")
    except ValueError:
        return None
    return parsed.replace(tzinfo=None, second=0, microsecond=0)


def book(view, request):
    """Create the request (or the confirmed booking) — see the module docstring."""
    tenant, patient, data = view.tenant, view.patient, request.data

    service_id, branch_id, doctor_id = _uuid(data.get("service")), _uuid(data.get("branch")), _uuid(data.get("doctor"))
    when = _slot(data.get("slot"))
    if when is None:
        return Response({"slot": ["اختر موعدًا من الأوقات المتاحة."]}, status=400)

    branch = Branch.objects.filter(uuid=branch_id).first() if branch_id else None
    doctor = Employee.objects.filter(uuid=doctor_id).first() if doctor_id else None
    service = Service.objects.filter(uuid=service_id).first() if service_id else None
    offer = resolve_offering(branch, doctor, service)
    if offer is None:
        return Response({"detail": NOT_BOOKABLE}, status=400)

    # A service sold by quantity (how many pulses, how many ml…) needs the patient
    # to say how many; the price is the contract's unit price × that. Anything
    # else ignores a quantity that is sent.
    quantity = None
    if service.requires_quantity:
        try:
            quantity = Decimal(str(data.get("quantity"))) if data.get("quantity") not in (None, "") else None
        except InvalidOperation:
            quantity = None
        if quantity is None and service.doctor_sets_quantity:
            quantity = service.min_quantity  # an estimate; the doctor sets the real one
        problem = quantity_problem(service, quantity)
        if problem:
            return Response({"quantity": [problem]}, status=400)
        quantity = quantity.quantize(Decimal("0.01"))

    if patient.branch_id and patient.branch_id != branch.pk and not tenant.portal_allow_other_branches:
        return Response({"branch": ["الحجز عبر الموقع متاح في عيادتك فقط."]}, status=403)

    live = Appointment.objects.filter(patient=patient)
    if live.filter(status="requested").count() >= MAX_PENDING_REQUESTS:
        return Response(
            {"detail": "لديك طلبات مواعيد لم تُؤكَّد بعد. انتظر رد العيادة."}, status=400
        )
    if live.filter(doctor=doctor, scheduled_date=when).exclude(status__in=("cancelled", "no_show")).exists():
        return Response({"detail": "لديك حجز بالفعل مع هذا الطبيب في هذا الوقت."}, status=400)

    notes = str(data.get("notes") or "").strip()[:1000]
    instant = branch.online_booking_confirms_at_once
    specialization = (
        service.specialization
        if service.specialization_id and doctor.specializations.filter(pk=service.specialization_id).exists()
        else None
    )

    # Atomic, so a failure after the INSERT — in a save signal, say — rolls the
    # row back instead of leaving a request the patient was told had failed.
    with transaction.atomic():
        if instant:
            # The doctor's row is the lock two simultaneous bookings queue on
            # (a no-op on SQLite, which serialises writers anyway).
            Employee.objects.select_for_update().get(pk=doctor.pk)
        if not is_offered(offer, when):
            return Response({"slot": [TAKEN]}, status=409)
        appointment = Appointment.objects.create(
            tenant=tenant, patient=patient, branch=branch, doctor=doctor, service=service,
            specialization=specialization,
            price=quantity_total(offer.price, quantity) if quantity is not None else (offer.price or 0),
            quantity=quantity, unit_price=offer.price if quantity is not None else None,
            quantity_is_estimate=bool(quantity is not None and service.doctor_sets_quantity),
            status="waiting" if instant else "requested",
            source=Appointment.Source.PUBLIC_PORTAL, scheduled_date=when,
            notes=f"{NOTE_PREFIX} {notes}".strip(),
        )
    from notifications import booking as told

    def announce():
        if instant:
            told.confirmed(appointment)
        else:
            told.request_received(appointment)
        told.online_request(appointment)

    transaction.on_commit(announce)
    from .views import appointment_payload

    return Response(appointment_payload(appointment), status=201)
