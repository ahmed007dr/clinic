"""Portal authentication — a cookie of its own, never a Django session.

The cookie is scoped to one clinic's portal path (`/api/portal/<slug>/`), is
`HttpOnly` so page script cannot read it, and holds a random token whose hash
is looked up **inside that clinic's tenant context** — so a token issued by one
clinic is simply not found under another, whatever the browser sends.

A staff session means nothing here, and a portal session means nothing to the
staff API: this authenticator reads only its own cookie, and the staff API
reads only Django's.
"""

from django.conf import settings
from django.utils import timezone
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, CSRFCheck
from rest_framework.permissions import BasePermission

from .models import SESSION_ABSOLUTE, PortalSession, hash_token

COOKIE = "portal_session"


def cookie_path(slug):
    return f"/api/portal/{slug}/"


def set_session_cookie(response, slug, token):
    response.set_cookie(
        COOKIE, token,
        max_age=int(SESSION_ABSOLUTE.total_seconds()),
        path=cookie_path(slug),
        secure=settings.SESSION_COOKIE_SECURE,
        httponly=True,
        samesite="Lax",
    )


def clear_session_cookie(response, slug):
    response.delete_cookie(COOKIE, path=cookie_path(slug), samesite="Lax")


def enforce_csrf(request):
    """Django's CSRF check, applied by hand.

    DRF only enforces CSRF inside `SessionAuthentication`, which the portal
    does not use — so without this every portal write, including login, would
    be forgeable from another site.
    """
    django_request = getattr(request, "_request", request)
    check = CSRFCheck(lambda _request: None)
    check.process_request(django_request)
    reason = check.process_view(django_request, None, (), {})
    if reason:
        raise exceptions.PermissionDenied(f"CSRF: {reason}")


class PortalPrincipal:
    """Who is making a portal request: a patient, never a staff user."""

    is_authenticated = True
    is_anonymous = False

    def __init__(self, session):
        self.session = session
        self.account = session.account
        self.patient = session.account.patient


class PortalAuthentication(BaseAuthentication):
    def authenticate(self, request):
        token = request.COOKIES.get(COOKIE)
        if not token:
            return None
        session = (
            PortalSession.objects.select_related("account__patient")
            .filter(token_hash=hash_token(token))
            .first()
        )
        if session is None or not session.is_live or not session.account.is_active:
            raise exceptions.AuthenticationFailed("انتهت الجلسة. سجّل الدخول مرة أخرى.")
        enforce_csrf(request)
        session.last_seen = timezone.now()
        session.save(update_fields=["last_seen"])
        return PortalPrincipal(session), session

    def authenticate_header(self, request):
        # Makes an unauthenticated portal call a 401, which the client reads as
        # "sign in", rather than a 403.
        return 'Portal realm="patient"'


class IsPortalPatient(BasePermission):
    message = "يجب تسجيل الدخول إلى بوابة المرضى."

    def has_permission(self, request, view):
        return isinstance(request.user, PortalPrincipal)
