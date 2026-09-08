from .context import reset_current_tenant, set_current_tenant


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
        try:
            return self.get_response(request)
        finally:
            reset_current_tenant(token)
