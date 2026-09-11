"""Who is platform staff, and what "act as tenant" is allowed to be.

The agreed shape (Tier 1) is: platform staff select **one** tenant explicitly,
the application enters that tenant's context on the **normal** connection, and
everything they see is read-only and audited. No BYPASSRLS role, no second
database connection, no bypass flag in the policies. The isolation model is
therefore unchanged — a connection is still always bound to exactly one tenant,
which is the invariant the whole design rests on.

Two things this deliberately does **not** do.

It does not touch `TenantMiddleware`. That middleware derives the tenant from
`request.user` and nothing else, on the grounds that reading it from a header,
a parameter or a session would turn switching clinics into a one-line attack.
Teaching it to honour a session value would put exactly that mechanism into
every request in the application. Instead the inspection views enter
`tenant_context` themselves, explicitly, for the duration of one read.

Writing into a clinic changed with the group owner's decision of 2026-09-11:
the platform has full control, medical records included. It still goes
through no bypass: a full administrator either changes platform-side records
(group, subscription, accounts) inside that group's `tenant_context`, or signs
in *as* one of the group's accounts for a limited time
(platform_admin/impersonation.py) — the ordinary clinic application, under
the ordinary tenant binding, announced to the group's owners and audited.
Support staff (`platform_role == "support"`) only ever read.
"""




def is_platform_staff(user):
    """Platform staff carry no tenant. That is the whole point of the flag: an
    operator belongs to the platform, not to a clinic.

    `is_superuser` is deliberately not the gate. It is a Django-admin concept
    and conflating the two is how a tenant administrator eventually acquires
    cross-tenant reach because somebody ticked a box in the wrong screen.
    """
    return bool(
        user
        and user.is_authenticated
        and user.is_active
        and getattr(user, "is_platform_staff", False)
        # A user who belongs to a clinic must never hold platform powers, even
        # if the flag gets set by mistake.
        and getattr(user, "tenant_id", None) is None
    )


def is_platform_super(user):
    """A full platform administrator — the only operator who may change
    anything. Support staff (`platform_role == "support"`) look, and that is
    all; an operator created before roles existed was migrated to "super"
    (accounts.0009)."""
    return is_platform_staff(user) and getattr(user, "platform_role", "") == "super"
