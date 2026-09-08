"""Who may see clinical data.

Reception books appointments, registers patients and handles payments, but
never sees a diagnosis — doc/readme.md §14 keeps Reception out of clinical
work and §87 asks for least privilege over medical data.

Any doctor in the clinic can read any of its patients' records, which is what
makes cover, handover and second opinions possible.
"""

CLINICAL_ROLES = {"Doctor", "Admin"}


def can_view_clinical(user):
    """Read access to clinical records. Fails closed for users with no role."""
    role = getattr(user, "role", None)
    return bool(role and role.name in CLINICAL_ROLES)


def scoped_to_user(queryset, user, branch_field="branch"):
    """Admins are org-wide by design; everyone else is limited to their branch.

    The tenant boundary is already applied by the model manager — this is the
    branch layer on top of it. `branch_field` is a lookup path because not
    every clinical model carries a branch of its own: a Prescription belongs
    to the branch of the visit that issued it.
    """
    role = getattr(user, "role", None)
    if role and role.name == "Admin":
        return queryset
    if getattr(user, "branch_id", None):
        return queryset.filter(**{branch_field: user.branch})
    return queryset.none()
