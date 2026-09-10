"""Who a clinic user is — decided in one place.

A medical group is a **Tenant**; each of its clinics is a **Branch**
(tenants/models.py). Row-level security already keeps one group's data away
from every other group, so the roles below only ever decide what happens
*inside* one group:

* **Owner** — owns the group. Sees every clinic and every figure, and has the
  group dashboard. The only role that can add clinics, see the subscription or
  the audit trail, change group-wide settings, or make someone an Owner.
* **Admin** — runs one clinic (their branch): its staff, its books, its
  reports. Sees that clinic only.
* **Doctor** — clinical work, in their clinic.
* **Reception** — the front desk, in their clinic.

Before the Owner role existed, "Admin" meant "sees every branch". Every Admin
at that moment was promoted to Owner (accounts.0007), so nobody's access
changed; from then on Admin means one clinic.

Every role check in the application goes through these functions. A role name
compared inline somewhere else is a check that will drift — which is exactly
how the old code ended up with forty-four slightly different ones.
"""

OWNER = "Owner"
ADMIN = "Admin"
DOCTOR = "Doctor"
RECEPTION = "Reception"

ALL_ROLES = (OWNER, ADMIN, DOCTOR, RECEPTION)

#: Who may read clinical records. Reception never does (§14).
CLINICAL_ROLES = {OWNER, ADMIN, DOCTOR}


def role_name(user):
    role = getattr(user, "role", None)
    return getattr(role, "name", None)


def is_owner(user):
    """Fails closed: a user with no role is nobody."""
    return role_name(user) == OWNER


def is_clinic_admin(user):
    """Administrative capability. An Owner is also an admin of every clinic."""
    return role_name(user) in {OWNER, ADMIN}


def sees_all_branches(user):
    """Only the Owner is group-wide. Everyone else, Admin included, sees their
    own clinic."""
    return is_owner(user)


def is_front_desk(user):
    """Registration, booking and payments."""
    return role_name(user) in {OWNER, ADMIN, RECEPTION}


def can_view_patients(user):
    return role_name(user) in {OWNER, ADMIN, RECEPTION, DOCTOR}


def can_view_clinical(user):
    return role_name(user) in CLINICAL_ROLES


def scope_queryset_to_user(queryset, user, branch_field="branch"):
    """The Owner sees every clinic; everyone else is held to their own.

    A user with no branch and no Owner role gets nothing rather than
    everything — the direction a mistake falls matters more than whether one
    happens. `branch_field` is a lookup path, because not every record has a
    branch of its own (a prescription belongs to its visit's clinic).
    """
    if sees_all_branches(user):
        return queryset
    branch_id = getattr(user, "branch_id", None)
    if branch_id:
        return queryset.filter(**{f"{branch_field}_id": branch_id})
    return queryset.none()


def assignable_role_names(user):
    """Roles this user may give to someone else.

    A clinic Admin staffs their clinic but can never create an Owner: that
    would be a clinic admin promoting themselves, or a friend, to see every
    clinic's books.
    """
    if is_owner(user):
        return {OWNER, ADMIN, DOCTOR, RECEPTION}
    if is_clinic_admin(user):
        return {ADMIN, DOCTOR, RECEPTION}
    return set()
