"""Sending an email and keeping a record of it.

Every message the system sends *for a clinic* goes through `deliver`, so the
clinic's staff (and the platform's support) can review what went out. It does
the sending and the logging together on purpose: a caller that logged
separately could forget to, or log a message that was never sent.

Sending never raises. An unreachable mail server must not turn a patient's
check-in or a doctor's payment into an error; the failure is recorded in the
log instead, where the clinic can see it.
"""

import logging
import re

from django.core.mail import EmailMessage

from tenants.context import tenant_context

from .models import EmailLog

logger = logging.getLogger(__name__)

#: kind → label. The list is the filter on the log screen, so a new kind is
#: added here and nowhere else.
KINDS = {
    "password_reset": "إعادة تعيين كلمة المرور",
    "portal_login_code": "رمز دخول بوابة المرضى",
    "portal_invitation": "دعوة إلى بوابة المرضى",
    "doctor_checkin": "إشعار الطبيب: دخول مريض",
    "doctor_payment": "إشعار الطبيب: نصيبه من دفعة",
    "personal_report": "تقرير شخصي",
    "daily_report": "التقرير اليومي",
    "monthly_report": "التقرير الشهري",
    "annual_report": "التقرير السنوي",
    "other": "أخرى",
}

#: Kinds that may be sent again from the log. The others carry a credential
#: (a sign-in code, a single-use link) and are stored masked, so there is
#: nothing faithful to send — a fresh code or invitation is issued instead.
RESENDABLE = {
    "daily_report", "monthly_report", "annual_report", "personal_report",
    "doctor_checkin", "doctor_payment",
}

MASK = "••••••"
_URL = re.compile(r"https?://\S+")


def mask_links(text):
    """Replace every link with a placeholder — for messages whose link is a
    credential."""
    return _URL.sub("[رابط مؤمَّن — غير محفوظ في السجل]", text)


def deliver(*, kind, tenant, to, subject, body, connection, sender, branch=None,
            html=False, template="", log_body=None, resent_from=None):
    """Send one message and log it. True when the mail server accepted it.

    `resent_from` marks a re-send of a logged message (api/views/email_log.py).
    `log_body` is what to store instead of `body` when the message carries a
    credential (see EmailLog). `connection`/`sender` come from
    platform_admin.mailer.sender_for; with none, nothing is sent or logged.
    """
    if connection is None or not to:
        return False
    recipients = [to] if isinstance(to, str) else list(to)
    message = EmailMessage(subject, body, from_email=sender, to=recipients, connection=connection)
    if html:
        message.content_subtype = "html"
    error = ""
    try:
        message.send()
    except Exception as caught:  # noqa: BLE001 — recorded, never raised
        error = caught.__class__.__name__
        logger.exception("Could not send %s email", kind)
    _record(kind, tenant, branch, recipients, sender, subject,
            body if log_body is None else log_body, html, template, error, resent_from)
    return not error


def _record(kind, tenant, branch, recipients, sender, subject, body, html, template, error, resent_from=None):
    """One row per recipient, so filtering by address finds the message. A
    failure to write the log is logged and swallowed: the message has already
    gone."""
    try:
        with tenant_context(tenant):
            for address in recipients:
                EmailLog.objects.create(
                    tenant=tenant, branch=branch, kind=kind if kind in KINDS else "other",
                    to_address=str(address)[:254], from_address=str(sender or "")[:254],
                    subject=str(subject)[:300], body=body, is_html=html, template=template,
                    status=EmailLog.Status.FAILED if error else EmailLog.Status.SENT, error=error,
                    resent_from=resent_from,
                )
    except Exception:  # noqa: BLE001
        logger.exception("Could not write the email log")
