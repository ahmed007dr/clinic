"""Role flags for the server-rendered templates.

Templates used to compare `user.role.name == 'Admin'` inline, twenty-six times.
They now read these flags, which come from `accounts/roles.py` — the same
functions every view and API endpoint uses.
"""

from .roles import is_clinic_admin, is_owner, sees_all_branches


def roles(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {"is_owner": False, "is_clinic_admin": False, "sees_all_branches": False}
    return {
        "is_owner": is_owner(user),
        "is_clinic_admin": is_clinic_admin(user),
        "sees_all_branches": sees_all_branches(user),
    }
