"""Telling people about a booking (docs/15, Phase 9).

Two audiences, both through what already exists — no new notification system:

* **The patient**, by e-mail through `notifications.maillog.deliver` (so every
  message shows in the clinic's e-mail log): the request was received, the
  booking was confirmed, cancelled or moved by the clinic, and a reminder the
  day before. Only patients who have an address and either belong to the
  website (a portal account, or a booking made from it) or agreed to e-mail.
  With no mail server anywhere nothing is sent — `deliver` sends and logs
  together and never raises, so a dead mail server can never stop a booking.
* **The clinic's staff**, in-app (`notifications.Notification`): a new website
  request, or the patient cancelling / asking to move a booking, reaches the
  reception and Admin of *that clinic* — the people who phone back.

Callers use `transaction.on_commit`, so nothing is sent for a booking that is
rolled back. SMS and WhatsApp join later as channels (portal/otp_channels.py's
idea) when a provider is enabled; nothing here changes then.
"""

import logging
from datetime import timedelta

from django.utils import timezone

from .maillog import deliver
from .models import Notification

logger = logging.getLogger(__name__)

#: Statuses in which a booking is still ahead and worth reminding about.
REMINDER_STATUSES = ("waiting", "quick")


def _when(moment):
    return moment.strftime("%Y-%m-%d — %H:%M") if moment else ""


def can_email_about(appointment):
    """The patient has an address, and is a website patient or agreed to e-mail."""
    patient = appointment.patient
    if not (patient.email or "").strip():
        return False
    from portal.models import PatientAccount

    return (
        patient.contact_by_email
        or appointment.source == "portal"
        or PatientAccount.all_objects.filter(patient=patient).exists()
    )


def _details(appointment):
    lines = []
    if appointment.service_id:
        lines.append(f"الخدمة: {appointment.service.name}")
    if appointment.doctor_id:
        lines.append(f"الطبيب: د. {appointment.doctor.name}")
    if appointment.branch_id:
        lines.append(f"العيادة: {appointment.branch.name}")
        if appointment.branch.address:
            lines.append(f"العنوان: {appointment.branch.address}")
        if appointment.branch.phone:
            lines.append(f"للتواصل: {appointment.branch.phone}")
    lines.append(f"الموعد: {_when(appointment.scheduled_date)}")
    return lines


def _email(kind, appointment, subject, intro, outro=()):
    """One message to the patient. False if not sent (no address, not wanted,
    no mail server)."""
    from platform_admin.mailer import sender_for

    if not can_email_about(appointment):
        return False
    tenant, patient = appointment.tenant, appointment.patient
    body = "\n".join([f"مرحباً {patient.name}،", "", intro, "", *_details(appointment), "", *outro]).strip()
    try:
        connection, sender = sender_for(branch=appointment.branch, customer=tenant)
        return deliver(
            kind=kind, tenant=tenant, branch=appointment.branch, to=patient.email.strip(),
            subject=f"{subject} — {tenant.name}", body=body, connection=connection, sender=sender,
        )
    except Exception:  # noqa: BLE001 — never stop a booking over an e-mail
        logger.exception("Could not send a %s e-mail", kind)
        return False


# ------------------------------------------------------------ to the patient


def request_received(appointment):
    return _email(
        "booking_received", appointment, "استلمنا طلب موعدك",
        "استلمت العيادة طلب موعدك، وستتصل بك لتحديد الموعد النهائي وتأكيده.",
        ["هذه رسالة آلية؛ لا حاجة للرد عليها."],
    )


def confirmed(appointment):
    return _email(
        "booking_confirmed", appointment, "تم تأكيد موعدك",
        "تم تأكيد موعدك.",
        ["الدفع عند الوصول للعيادة. إن أردت تغيير الموعد أو إلغاءه فمن حسابك في بوابة المرضى أو بالاتصال بالعيادة."],
    )


def cancelled_by_clinic(appointment):
    return _email(
        "booking_cancelled", appointment, "تم إلغاء موعدك",
        "نأسف، تم إلغاء هذا الحجز من العيادة. للاستفسار أو لحجز موعد آخر تواصل مع العيادة.",
    )


def time_changed(appointment, old_time):
    return _email(
        "booking_changed", appointment, "تم تعديل موعدك",
        f"عدّلت العيادة موعدك (كان {_when(old_time)}). الموعد الجديد أدناه.",
    )


def reminder(appointment):
    return _email(
        "booking_reminder", appointment, "تذكير بموعدك غداً",
        "نذكّرك بموعدك القادم في العيادة.",
        ["إن تعذّر الحضور فنرجو إبلاغ العيادة أو تعديل الحجز من بوابة المرضى."],
    )


def status_changed(appointment, old_status):
    """Called after the clinic moves a booking between statuses."""
    new = appointment.status
    if old_status == "requested" and new == "waiting":
        return confirmed(appointment)
    if new == "cancelled" and old_status in ("requested", "waiting", "quick"):
        return cancelled_by_clinic(appointment)
    return False


# ------------------------------------------------------------ to the staff


def staff_of(branch_id):
    """Active reception and Admin logins of one clinic — who phones back."""
    from accounts.models import User

    return User.objects.filter(
        branch_id=branch_id, is_active=True, role__name__in=("Reception", "Admin"),
    )


def tell_staff(appointment, title, message):
    """An in-app notice for the clinic's front desk. Never raises."""
    if not appointment.branch_id:
        return 0
    try:
        users = list(staff_of(appointment.branch_id))
        for user in users:
            Notification.objects.create(
                tenant=appointment.tenant, user=user, type="appointment", title=title, message=message,
            )
        return len(users)
    except Exception:  # noqa: BLE001
        logger.exception("Could not notify the clinic's staff")
        return 0


def online_request(appointment):
    """A booking arrived from the website: a request to phone back about, or —
    at a clinic that confirms at once — a booking that is already settled."""
    name = appointment.patient.name
    what = appointment.service.name if appointment.service_id else "موعد"
    doctor = f" مع د. {appointment.doctor.name}" if appointment.doctor_id else ""
    if appointment.status == "requested":
        return tell_staff(
            appointment, "طلب موعد جديد من الموقع",
            f"{name} — {what}{doctor} — الوقت المفضّل {_when(appointment.scheduled_date)}. اتصل به لتأكيد الموعد.",
        )
    return tell_staff(
        appointment, "حجز مؤكَّد جديد من الموقع",
        f"{name} — {what}{doctor} — {_when(appointment.scheduled_date)}.",
    )


def quantity_set(appointment, old_total, new_total):
    """The doctor fixed the real quantity: tell the desk what is left to collect —
    or that more was paid than the service now comes to."""
    from billing.collect import amount_paid, money

    paid = amount_paid(appointment)
    net = max(new_total - (appointment.discount or 0), 0)
    unit = appointment.service.quantity_unit if appointment.service_id else ""
    lines = [
        f"{appointment.patient.name}: حدد الطبيب الكمية {appointment.quantity.normalize():f} {unit}".strip(),
        f"— الإجمالي الآن {money(new_total)} (كان {money(old_total)}).",
    ]
    if paid < net:
        lines.append(f"المتبقي للتحصيل {money(net - paid)}.")
    elif paid > net:
        lines.append(f"المدفوع أكبر من الإجمالي بمقدار {money(paid - net)}؛ يلزم رد الفرق للمريض.")
    return tell_staff(appointment, "الطبيب حدد كمية الخدمة", " ".join(lines))


def patient_cancelled(appointment):
    return tell_staff(
        appointment, "ألغى المريض حجزه",
        f"{appointment.patient.name} ألغى حجز {_when(appointment.scheduled_date)} من البوابة.",
    )


def patient_asked_to_move(appointment):
    return tell_staff(
        appointment, "طلب تغيير موعد",
        f"{appointment.patient.name} يطلب نقل حجز {_when(appointment.scheduled_date)} إلى "
        f"{_when(appointment.reschedule_requested_for)}. اتصل به لتأكيد الموعد الجديد.",
    )


# ------------------------------------------------------------ reminders


def send_reminders(tenant, day=None):
    """E-mail the reminder for every still-ahead booking of `tenant` on `day`
    (tomorrow by default) whose patient may be e-mailed. Returns how many were
    handed to the mail server. Run once a day (cron), inside the tenant's
    context; sending twice the same day is prevented by the e-mail log."""
    from appointments.models import Appointment

    from .models import EmailLog

    day = day or (timezone.now().date() + timedelta(days=1))
    sent = 0
    for appointment in (
        Appointment.objects.filter(scheduled_date__date=day, status__in=REMINDER_STATUSES)
        .select_related("patient", "doctor", "service", "branch")
    ):
        to = (appointment.patient.email or "").strip()
        if not to or not can_email_about(appointment):
            continue
        already = EmailLog.objects.filter(
            kind="booking_reminder", to_address=to, subject__contains=tenant.name,
            body__contains=_when(appointment.scheduled_date),
            created_at__date=timezone.now().date(),
        ).exists()
        if already:
            continue
        sent += 1 if reminder(appointment) else 0
    return sent
