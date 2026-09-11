"""Emails to a doctor about their own patients and their own money.

The group owner's rule (2026-09-11): when a patient is sent in to a doctor,
or money is received for one of their bookings, the doctor gets an email with
the full detail — the service, its original price, their percentage and their
share. Only ever about that doctor's own work.

Sent after the transaction commits (callers use `transaction.on_commit`), to
the doctor record's email or else their login's. A failure to send is
logged, never raised: an unreachable mail server must not stop the front desk
checking a patient in or taking a payment. With no mail server configured
nothing is sent at all.
"""

import logging

from django.conf import settings
from django.core.mail import EmailMessage, get_connection

logger = logging.getLogger(__name__)

#: Seconds before giving up on the mail server. Django's default is to wait
#: forever, which on a hung SMTP host would hang the request with it.
TIMEOUT = 10


def _recipient(doctor):
    if doctor is None:
        return None
    if doctor.email:
        return doctor.email
    account = getattr(doctor, "user_account", None)
    return getattr(account, "email", None) or None


def _send(doctor, subject, lines):
    to = _recipient(doctor)
    # No mail server configured: nothing to send through. (The in-memory
    # backend the test runner installs needs none.)
    configured = bool(getattr(settings, "EMAIL_HOST", None)) or "locmem" in settings.EMAIL_BACKEND
    if not to or not configured:
        return False
    try:
        connection = get_connection(timeout=TIMEOUT)
        EmailMessage(subject, "\n".join(lines), to=[to], connection=connection).send()
        return True
    except Exception:  # noqa: BLE001 — see the module docstring
        logger.exception("Could not email doctor %s", getattr(doctor, "pk", None))
        return False


def _money(value):
    return f"{value:,.2f} ج.م" if value is not None else "—"


def email_doctor_checkin(appointment_id):
    """A patient has been sent in to the doctor."""
    from appointments.models import Appointment

    from .pricing import percent_for, price_for

    appointment = (
        Appointment.all_objects.select_related("patient", "doctor", "service", "branch")
        .filter(pk=appointment_id).first()
    )
    if appointment is None or appointment.doctor is None:
        return False
    doctor, service = appointment.doctor, appointment.service
    price = appointment.price or price_for(doctor, service)
    percent = percent_for(doctor, service)
    lines = [
        f"د. {doctor.name}،",
        "",
        f"دخل إليك المريض: {appointment.patient.name}",
        f"الفرع: {getattr(appointment.branch, 'name', '—')}",
        f"الموعد: {appointment.scheduled_date:%Y-%m-%d %H:%M}",
        f"الخدمة / الكشف: {getattr(service, 'name', None) or 'كشف'}",
        f"السعر الأصلي: {_money(price)}",
        f"نسبتك: {percent}%" if percent is not None else "نسبتك: غير محددة في تعاقدك بعد",
        "",
        "تُحتسب نسبتك من المبلغ المدفوع فعلاً، وتصلك رسالة عند استلامه.",
    ]
    return _send(doctor, f"دخول مريض: {appointment.patient.name}", lines)


def email_doctor_payment(commission_id):
    """Money has been received for one of the doctor's bookings."""
    from .models import DoctorCommission

    commission = (
        DoctorCommission.all_objects.select_related("doctor", "patient", "branch", "payment")
        .filter(pk=commission_id).first()
    )
    if commission is None:
        return False
    lines = [
        f"د. {commission.doctor.name}،",
        "",
        f"تم استلام مبلغ من المريض: {getattr(commission.patient, 'name', '—')}",
        f"الفرع: {getattr(commission.branch, 'name', '—')}",
        f"رقم الإيصال: {getattr(commission.payment, 'receipt_number', '—')}",
        f"الخدمة / الكشف: {commission.description}",
        f"السعر الأصلي: {_money(commission.original_price)}",
        f"المبلغ المدفوع: {_money(commission.paid_amount)}",
        f"نسبتك: {commission.percent}%",
        f"نصيبك: {_money(commission.amount)}",
        f"الحالة: {commission.get_status_display()}",
    ]
    return _send(commission.doctor, f"نصيبك من دفعة {getattr(commission.patient, 'name', '')}", lines)
