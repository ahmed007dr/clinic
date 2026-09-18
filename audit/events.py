"""Sign-in and sign-out, written to the audit log.

This used to live inside the old server-rendered login screen, so a sign-in
through the React app — the only way in now — was never recorded. It is called
from the API's login, second-factor and logout views instead.

A failure to write is logged and swallowed: an audit table that cannot be
written must not lock the clinic out of its own system.
"""

import logging

from .models import AuditLog

logger = logging.getLogger(__name__)


def record_sign_in(request, user, *, description="User logged in"):
    _record(request, user, "login", description)


def record_sign_out(request, user):
    _record(request, user, "logout", "User logged out")


def _record(request, user, action, description):
    try:
        AuditLog.objects.create(
            tenant=getattr(user, "tenant", None),
            user=user,
            action=action,
            description=description,
            ip_address=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT"),
        )
    except Exception:  # noqa: BLE001 — see the module docstring
        logger.exception("Could not audit %s for user %s", action, getattr(user, "pk", None))
