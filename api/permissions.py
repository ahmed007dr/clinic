"""Who may call what.

Every rule here already exists in the server-rendered views. None of it is new
policy, and that is deliberate: an API that invents its own authorization is an
API that disagrees with the screens, and the disagreement is always discovered
by whoever finds the looser of the two.

The layers, outermost first:

1. **Tenant.** Not enforced here at all. `TenantMiddleware` binds the tenant
   from `request.user`, `TenantManager` filters to it, and PostgreSQL row-level
   security backs both. An API view that forgot every check below would still
   be unable to read another clinic's rows.
2. **Authentication.** Session-based; see `api/authentication.py`.
3. **Role.** Admin, Doctor, Reception — `IsClinicAdmin`, `CanViewClinical`.
4. **Branch.** Admin is clinic-wide; everyone else sees their own branch.

Layer 4 is a queryset filter rather than a permission class, because it decides
*which rows*, not *whether the call is allowed* — a receptionist listing
patients gets their branch's patients and a 200, not a 403.
"""

from rest_framework import permissions

from medical.permissions import CLINICAL_ROLES, can_view_clinical

# Re-exported so callers have one import for the whole policy.
__all__ = [
    "CLINICAL_ROLES",
    "CanViewClinical",
    "IsClinicAdmin",
    "IsClinicMember",
    "ReadOnlyForNonAdmin",
    "can_view_clinical",
    "is_clinic_admin",
    "scope_queryset_to_user",
]


def role_name(user):
    role = getattr(user, "role", None)
    return getattr(role, "name", None)


def is_clinic_admin(user):
    """Fails closed: a user with no role is not an admin."""
    return role_name(user) == "Admin"


def scope_queryset_to_user(queryset, user, branch_field="branch"):
    """Admin is clinic-wide by design; everyone else is held to their branch.

    Deliberately the same function `medical/permissions.py` applies to clinical
    records, extended to the rest of the API. Two of the older screens
    (patients, appointments) narrow only for Reception, which left a Doctor
    seeing every branch's list; the API applies the stricter clinical rule
    everywhere instead of copying that inconsistency forward.

    A user with no branch and no admin role gets nothing rather than
    everything — the direction a mistake falls matters more than whether one
    happens.
    """
    if is_clinic_admin(user):
        return queryset
    branch_id = getattr(user, "branch_id", None)
    if branch_id:
        return queryset.filter(**{f"{branch_field}_id": branch_id})
    return queryset.none()


class IsClinicMember(permissions.BasePermission):
    """Authenticated, and a member of some clinic.

    Platform staff carry `tenant = None` and are excluded on purpose: they have
    their own audited, read-only, explicitly-scoped route into a tenant
    (`platform_admin`), and letting them fall through to the ordinary API would
    quietly turn that into unrestricted cross-tenant access.
    """

    message = "هذا الحساب غير مرتبط بعيادة."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and getattr(user, "tenant_id", None) is not None
        )


class IsClinicAdmin(IsClinicMember):
    """Administrative surfaces: staff accounts, branches, plans, settings."""

    message = "هذا الإجراء مقصور على مدير العيادة."

    def has_permission(self, request, view):
        return super().has_permission(request, view) and is_clinic_admin(request.user)


class ReadOnlyForNonAdmin(IsClinicMember):
    """Everyone in the clinic may read; only an Admin may change.

    For reference data — services, branches, expense categories — that
    reception needs to *see* in order to do its job and has no business
    editing.
    """

    message = "التعديل مقصور على مدير العيادة."

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return is_clinic_admin(request.user)


class CanViewClinical(IsClinicMember):
    """Clinical records: visits, prescriptions, plans, procedures, labs, files.

    Reception books appointments, registers patients and takes payments, and
    never sees a diagnosis. This is the API half of that rule; the other half
    is that no clinical field appears in any serializer reception can reach.
    """

    message = "الاطلاع على السجلات الطبية مقصور على الأطباء ومدير العيادة."

    def has_permission(self, request, view):
        return super().has_permission(request, view) and can_view_clinical(request.user)
