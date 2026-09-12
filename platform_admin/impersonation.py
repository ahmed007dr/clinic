""""Login as" — a developer working inside a group as one of its accounts.

The group owner's decision (2026-09-11): yes, for support, and it is how the
platform reaches (and may change) a clinic's medical records. The guard rails:

* full administrators only, with a reason, for 5 to 120 minutes;
* recorded as a `SupportSession`, written to the group's audit trail, and
  announced to the group's owners as a notification — the clinic can see
  that it happened, by whom and why;
* every change made meanwhile is audited under the account used, marked
  "[support: <operator>]" (audit/signals.py);
* the session ends by itself when the time is up (SupportSessionMiddleware):
  the browser is signed out, never returned to the operator's own session.
  Ending it by hand returns the operator to the portal.
"""

import time
from datetime import timedelta

from django.contrib.auth import get_user_model, login, logout
from django.utils import timezone

from tenants.context import tenant_context

from .models import SupportSession

#: Session key while signed in as someone else.
SESSION_KEY = "platform_support"
BACKEND = "django.contrib.auth.backends.ModelBackend"
MIN_MINUTES, MAX_MINUTES = 5, 120


class SupportError(ValueError):
    """The message is for the operator."""


def current(request):
    """The running support session's details, or None."""
    session = getattr(request, "session", None)
    return session.get(SESSION_KEY) if session is not None else None


def start(request, target, reason, minutes=30, before_login=None):
    from accounts.middleware import TWO_FACTOR_KEY

    operator = request.user
    reason = (reason or "").strip()
    if not reason:
        raise SupportError("اكتب سبب الدخول.")
    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        raise SupportError("المدة بالدقائق.")
    if not MIN_MINUTES <= minutes <= MAX_MINUTES:
        raise SupportError(f"المدة من {MIN_MINUTES} إلى {MAX_MINUTES} دقيقة.")
    if target.tenant_id is None or getattr(target, "is_platform_staff", False):
        raise SupportError("لا يمكن الدخول بهذا الحساب.")
    if not target.is_active:
        raise SupportError("الحساب موقوف؛ فعّله أولاً.")
    if not request.session.get(TWO_FACTOR_KEY):
        raise SupportError("أكمل التحقق بخطوتين أولاً.")

    tenant = target.tenant
    expires = timezone.now() + timedelta(minutes=minutes)
    log = SupportSession.objects.create(
        operator=operator, customer=tenant, target=target, reason=reason[:300], expires_at=expires,
        ip_address=request.META.get("REMOTE_ADDR"),
    )
    _announce(tenant, operator, target, reason, minutes)
    if before_login is not None:
        before_login(log)

    operator_email = operator.email
    # login() flushes the operator's session: a different user signs in.
    login(request, target, backend=BACKEND)
    request.session[SESSION_KEY] = {
        "id": log.pk,
        "operator": operator.pk,
        "operator_email": operator_email,
        "until": int(time.time()) + minutes * 60,
        "target": target.username,
        "group": tenant.name,
    }
    request.session.set_expiry(minutes * 60)
    return log


def _announce(tenant, operator, target, reason, minutes):
    """Tell the group's owners — the clinic must be able to see it."""
    from notifications.models import Notification

    User = get_user_model()
    with tenant_context(tenant):
        owners = User.objects.filter(tenant=tenant, role__name="Owner", is_active=True)
        for owner in owners:
            Notification.objects.create(
                tenant=tenant, user=owner, type="warning",
                title="دخول الدعم الفني للمنصة",
                message=(
                    f"دخل الدعم الفني ({operator.email}) إلى حسابكم باسم «{target.username}» "
                    f"لمدة أقصاها {minutes} دقيقة. السبب: {reason}"
                ),
            )


def _close(info):
    SupportSession.objects.filter(pk=info.get("id"), ended_at__isnull=True).update(ended_at=timezone.now())


def end(request):
    """Back to the operator's own portal session (the second step counts as
    done: it was, to begin the support session)."""
    from accounts.middleware import TWO_FACTOR_KEY
    from api.views.auth import PLATFORM_SESSION_SECONDS

    info = current(request)
    if not info:
        raise SupportError("لا توجد جلسة دعم.")
    _close(info)
    operator = get_user_model().objects.filter(pk=info["operator"], is_active=True).first()
    if operator is None:
        logout(request)
        return None
    login(request, operator, backend=BACKEND)
    request.session[TWO_FACTOR_KEY] = True
    request.session.set_expiry(PLATFORM_SESSION_SECONDS)
    return operator


def expire_if_due(request):
    """True when the support session was over and has been ended."""
    info = current(request)
    if not info:
        return False
    ended = SupportSession.objects.filter(pk=info.get("id"), ended_at__isnull=False).exists()
    if time.time() < info.get("until", 0) and not ended:
        return False
    _close(info)
    logout(request)
    return True
