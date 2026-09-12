"""Emails from the platform itself — to people asking to open a clinic, and
to the platform's own administrators.

Sent through the platform's mail server (vault scope "platform", else the
settings file; platform_admin/mailer.py). A failure is logged, never raised:
an unreachable mail server must not lose a signup request or an approval.
"""

import logging

from django.contrib.auth import get_user_model
from django.core.mail import EmailMessage

from .mailer import sender_for

logger = logging.getLogger(__name__)


def send(to, subject, lines):
    recipients = [address for address in ([to] if isinstance(to, str) else to) if address]
    if not recipients:
        return False
    try:
        connection, sender = sender_for()
        if connection is None:
            return False
        EmailMessage(subject, "\n".join(lines), from_email=sender, to=recipients, connection=connection).send()
        return True
    except Exception:  # noqa: BLE001 — see the module docstring
        logger.exception("Could not send platform email %r", subject)
        return False


def operators():
    """The full administrators' addresses."""
    User = get_user_model()
    return list(
        User.objects.filter(is_platform_staff=True, tenant__isnull=True, is_active=True, platform_role="super")
        .exclude(email="").values_list("email", flat=True)
    )
