"""Recording what platform staff did.

The requirement is that platform access is audited, and reads matter as much as
writes here: the sensitive act is a SaaS operator opening a clinic's record at
all. The change-tracking signals in `audit/` only fire on save and delete, so a
read leaves no trace on its own — this module is what makes inspection visible.

Entries are written against the **inspected** tenant, not against the operator's
own (they have none), so a clinic's audit trail contains the fact that the
platform looked. That is the entry a customer would want to be able to find.
"""

from audit.models import AuditLog


def record(request, tenant, action, description, model_name="", object_id=""):
    """Write one platform-staff audit entry.

    Failures are allowed to propagate rather than being swallowed. Elsewhere
    auditing is best-effort, because losing an audit row is better than failing
    a clinician's save. Here the audit *is* the control: an inspection that
    cannot be recorded should not happen.
    """
    return AuditLog.objects.create(
        tenant=tenant,
        user=request.user if request.user.is_authenticated else None,
        action="custom",
        model_name=model_name or "platform",
        object_id=str(object_id or (tenant.pk if tenant else "")),
        description=f"[platform] {action}: {description}",
        ip_address=request.META.get("REMOTE_ADDR"),
        user_agent=request.META.get("HTTP_USER_AGENT"),
    )
