"""Carry a doctor's chosen clinic from the session onto the user.

A doctor linked to several clinics picks which one they are looking at
(`POST /api/auth/branch/`). The pick lives in the session; this puts it on
`request.user.active_branch_id`, where `accounts.roles.current_branch_id`
reads it — and re-validates it — for every scoping decision in the request.

Must follow AuthenticationMiddleware.
"""

SESSION_KEY = "active_branch_id"


class ActiveBranchMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        chosen = request.session.get(SESSION_KEY) if hasattr(request, "session") else None
        if chosen:
            user = request.user
            if user.is_authenticated:
                user.active_branch_id = chosen
        return self.get_response(request)


#: Set by the second step of a platform sign-in (api/views/auth.py).
TWO_FACTOR_KEY = "platform_2fa_ok"
#: How often, at most, an account's last activity is written.
LAST_SEEN_EVERY = 60


class PlatformTwoFactorMiddleware:
    """No platform session without the second step — through any door.

    A platform operator reaches every clinic, so a password alone must never
    be enough. Rather than guard each way in (the API sign-in, the older
    server-rendered sign-in page, anything added later), a session that belongs
    to a platform operator and was not completed with a one-time code is ended
    here, before any view runs. Must follow AuthenticationMiddleware.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            user is not None
            and user.is_authenticated
            and getattr(user, "is_platform_staff", False)
            and not request.session.get(TWO_FACTOR_KEY)
        ):
            from django.contrib.auth import logout
            from django.contrib.auth.models import AnonymousUser

            logout(request)
            request.user = AnonymousUser()
        return self.get_response(request)


class SupportSessionMiddleware:
    """Ends a developer's "login as" session the moment its time is up (or
    it was ended from the portal) — platform_admin/impersonation.py. Must
    follow AuthenticationMiddleware."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from platform_admin.impersonation import expire_if_due

        if hasattr(request, "session") and expire_if_due(request):
            from django.contrib.auth.models import AnonymousUser

            request.user = AnonymousUser()
        return self.get_response(request)


class LastSeenMiddleware:
    """Remember when each account was last active, for "online now" and "last
    seen" on the platform portal. One UPDATE a minute per active user at most,
    written straight to the row — no signals, no audit entry, no save()."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.contrib.auth import get_user_model

        # Taken before the view runs: the patient portal's API replaces
        # request.user with a patient, who is not an account and has no row
        # here.
        user = getattr(request, "user", None)
        response = self.get_response(request)
        # A developer signed in as someone for support is not that person
        # being online.
        supporting = hasattr(request, "session") and request.session.get("platform_support")
        if isinstance(user, get_user_model()) and user.is_authenticated and not supporting:
            from django.utils import timezone

            now = timezone.now()
            last = getattr(user, "last_seen_at", None)
            if last is None or (now - last).total_seconds() >= LAST_SEEN_EVERY:
                # request.user is a lazy wrapper; go through the model itself.
                get_user_model().objects.filter(pk=user.pk).update(last_seen_at=now)
        return response
