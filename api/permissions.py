"""Who may call what.

Every rule here comes from `accounts/roles.py`, the one place role names are
interpreted. The API and the server-rendered screens ask the same functions,
because an API that invents its own authorization is an API that disagrees with
the screens — and the disagreement is always found by whoever finds the looser
of the two.

The layers, outermost first:

1. **Tenant (the medical group).** Not enforced here at all. `TenantMiddleware`
   binds the tenant from `request.user`, `TenantManager` filters to it, and
   PostgreSQL row-level security backs both. One group can never reach
   another's data, whatever a view forgets.
2. **Authentication.** Session-based; see `api/views/auth.py`.
3. **Role.** Owner, Admin, Doctor, Reception — see `accounts/roles.py`.
4. **Clinic (branch).** The Owner sees every clinic; everyone else their own.

Layer 4 is a queryset filter rather than a permission class, because it decides
*which rows*, not *whether the call is allowed*.
"""

from rest_framework import permissions

from accounts.roles import (
    CLINICAL_ROLES,
    can_view_clinical,
    is_clinic_admin,
    is_owner,
    role_name,
    scope_queryset_to_user,
    sees_all_branches,
)

# Re-exported so callers have one import for the whole policy.
__all__ = [
    "CLINICAL_ROLES",
    "CanViewClinical",
    "IsClinicAdmin",
    "IsClinicMember",
    "IsGroupOwner",
    "ReadOnlyForNonAdmin",
    "ReadOnlyForNonOwner",
    "can_view_clinical",
    "is_clinic_admin",
    "is_group_owner",
    "role_name",
    "scope_queryset_to_user",
    "sees_all_branches",
]

is_group_owner = is_owner


class IsClinicMember(permissions.BasePermission):
    """Authenticated, a member of some clinic group, and that group active.

    Platform staff carry `tenant = None` and are excluded on purpose: they have
    their own audited, explicitly-scoped route into a tenant, and letting them
    fall through to the ordinary API would quietly turn that into unrestricted
    cross-tenant access.
    """

    message = "هذا الحساب غير مرتبط بعيادة."

    def has_permission(self, request, view):
        user = request.user
        if not (
            user
            and user.is_authenticated
            and getattr(user, "tenant_id", None) is not None
        ):
            return False
        # Checked on every request, not only at sign-in: suspending a clinic
        # must stop its staff now, not whenever their sessions happen to
        # expire.
        if not user.tenant.is_usable:
            self.message = "اشتراك العيادة غير نشط. يرجى التواصل مع الدعم."
            return False
        return True


class IsClinicAdmin(IsClinicMember):
    """Administrative work — for the Owner (every clinic) or a clinic Admin
    (their own clinic, which the querysets enforce)."""

    message = "هذا الإجراء مقصور على إدارة العيادة."

    def has_permission(self, request, view):
        return super().has_permission(request, view) and is_clinic_admin(request.user)


class IsGroupOwner(IsClinicMember):
    """The whole group: the owner dashboard, clinics, the subscription, group
    settings. A clinic Admin is refused — being in charge of one clinic is not
    being in charge of all of them."""

    message = "هذا القسم مقصور على مالك المجموعة."

    def has_permission(self, request, view):
        return super().has_permission(request, view) and is_owner(request.user)


class ReadOnlyForNonAdmin(IsClinicMember):
    """Everyone may read; only an admin may change. For shared reference data
    that the front desk needs to see — services, categories, specialties."""

    message = "التعديل مقصور على إدارة العيادة."

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return is_clinic_admin(request.user)


class ReadOnlyForNonOwner(IsClinicMember):
    """Everyone may read; only the Owner may change. For the group's own
    structure — its clinics and its roles — which one clinic's admin must not
    reshape for everyone else."""

    message = "التعديل مقصور على مالك المجموعة."

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return is_owner(request.user)


class CanViewClinical(IsClinicMember):
    """Clinical records. Reception books, registers and takes payment, and
    never sees a diagnosis."""

    message = "الاطلاع على السجلات الطبية مقصور على الأطباء والإدارة."

    def has_permission(self, request, view):
        return super().has_permission(request, view) and can_view_clinical(request.user)
