"""A visit begins when the front desk sends the patient in.

The group owner's rule (2026-09-11): a visit is registered by reception, not
typed up by the doctor. So the moment a booking moves to "entered" (تم الدخول)
the visit exists — for that booking's patient, doctor and clinic, dated now —
and those four facts are fixed from then on (api/serializers/clinical.py). The
doctor finds the patient waiting in their room (`in_room`) and writes the
clinical part; reception never sees it.

Driven by a post_save signal on Appointment, so the React API, the older
server-rendered queue and anything else that moves a booking all create the
visit the same way.
"""

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

ENTERED = "entered"


def ensure_visit(appointment, user=None):
    """The visit for a booking that has been sent in; created once."""
    from .models import Visit

    existing = Visit.all_objects.filter(appointment=appointment).first()
    if existing is not None:
        return existing
    return Visit.all_objects.create(
        tenant_id=appointment.tenant_id,
        appointment=appointment,
        patient_id=appointment.patient_id,
        doctor_id=appointment.doctor_id,
        branch_id=appointment.branch_id or getattr(appointment.patient, "branch_id", None),
        visit_date=timezone.now(),
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )


def in_room(user):
    """Today's bookings the doctor has been sent, oldest first, each with its
    visit. Empty for anyone who is not a linked doctor."""
    from appointments.models import Appointment

    from accounts.roles import is_doctor, scope_queryset_to_user

    employee_id = getattr(user, "employee_id", None)
    if not is_doctor(user) or not employee_id:
        return []
    bookings = (
        scope_queryset_to_user(Appointment.objects.all(), user)
        .filter(status=ENTERED, scheduled_date__date=timezone.now().date())
        .select_related("patient")
        .order_by("scheduled_date")
    )
    return [(booking, ensure_visit(booking, user)) for booking in bookings]


@receiver(post_save, sender="appointments.Appointment")
def visit_on_entry(sender, instance, **kwargs):
    if instance.status != ENTERED:
        return
    from audit.middleware import get_current_request

    from .models import Visit

    if Visit.all_objects.filter(appointment=instance).exists():
        return
    request = get_current_request()
    ensure_visit(instance, getattr(request, "user", None))
    # The doctor hears about it: who, what service, the price and their share
    # (billing/notify.py). Once, when the visit opens.
    from billing.notify import email_doctor_checkin

    transaction.on_commit(lambda: email_doctor_checkin(instance.pk))
