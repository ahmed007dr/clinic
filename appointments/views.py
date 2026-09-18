"""The queue ticket, the one server-rendered page of appointments that the React
app links to (to print). Bookings themselves are the React app and the API."""

from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import models
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from accounts.roles import display_name, is_front_desk, scope_queryset_to_user

from .models import Appointment


def is_reception_or_admin(user):
    return is_front_desk(user)


#: The queue ticket only makes sense before the patient has gone in — once
#: they are "entered" they are already with the doctor, and after that it is
#: history, not something to hand someone waiting.
TICKET_STATUSES = ("waiting", "called")


#: Who counts as "ahead" for the "متبقي" count: also "entered", since someone
#: already with the doctor is certainly ahead of someone still waiting.
QUEUE_STATUSES = ("waiting", "called", "entered")


@login_required
@user_passes_test(is_reception_or_admin)
def appointment_ticket_print(request, uuid):
    """The slip handed to a patient who is now waiting: check-in time, their
    doctor, how many are ahead of them for that doctor, who printed it and
    when (the group owner's rule, 2026-09-12) — so nobody forgets when they
    arrived or loses their place in the queue.

    Printable only for today's booking still waiting to be seen; the design —
    which of these lines show at all — is the clinic's own (branches.printing,
    api/views/print_settings.py).
    """
    from branches.printing import letterhead, ticket_layout

    appointment = get_object_or_404(
        scope_queryset_to_user(Appointment.objects.select_related("patient", "doctor", "branch"), request.user),
        uuid=uuid,
    )
    today = timezone.now().date()
    if appointment.status not in TICKET_STATUSES or appointment.scheduled_date.date() != today:
        return render(request, "print/_unavailable.html", {
            "message": "لا يمكن طباعة تذكرة الانتظار — الحجز ليس ضمن قائمة الانتظار اليوم.",
        })

    ahead_count = None
    if appointment.doctor_id is not None:
        ahead_count = Appointment.objects.filter(
            branch=appointment.branch, doctor_id=appointment.doctor_id,
            scheduled_date__date=today, status__in=QUEUE_STATUSES,
        ).filter(
            models.Q(scheduled_date__lt=appointment.scheduled_date)
            | models.Q(scheduled_date=appointment.scheduled_date, id__lt=appointment.id)
        ).count()

    return render(request, "appointments/ticket_print.html", {
        "letterhead": letterhead(appointment.branch, request),
        "layout": ticket_layout(appointment.branch),
        "appointment": appointment,
        "ahead_count": ahead_count,
        "checked_in_at": timezone.now(),
        "reception_name": display_name(request.user),
    })
