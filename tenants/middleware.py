from .context import (
    bind_database_tenant,
    reset_current_tenant,
    restore_database_tenant,
    set_current_tenant,
)


class TenantMiddleware:
    """Binds the current tenant for the duration of a request.

    The tenant is derived from the authenticated user and nowhere else.
    Reading it from a header, query parameter or URL segment would turn
    switching between clinics into a one-line attack.

    Must sit after AuthenticationMiddleware, which is what populates
    request.user.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        tenant = user.tenant if (user is not None and user.is_authenticated) else None

        token = set_current_tenant(tenant)
        previous = bind_database_tenant(tenant)
        try:
            if tenant is not None:
                self.shut_out_stopped_clinic(request)
            return self.get_response(request)
        finally:
            reset_current_tenant(token)
            restore_database_tenant(previous)

    @staticmethod
    def shut_out_stopped_clinic(request):
        """End the session of someone whose clinic the Owner has stopped.

        Here rather than in an authentication backend because the check reads
        the user's branch, and under row-level security that row is only
        visible once the tenant is bound — which is this middleware's job.
        Django's own backend already does the same for a deactivated account.
        The request then carries on as anonymous: the API answers 401 and the
        older screens send the person to the sign-in page.
        """
        from django.contrib.auth import logout
        from django.contrib.auth.models import AnonymousUser

        from accounts.roles import account_is_usable

        if not account_is_usable(request.user):
            logout(request)
            request.user = AnonymousUser()
