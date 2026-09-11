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
