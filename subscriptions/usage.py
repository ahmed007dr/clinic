"""How much of its plan a clinic has used — counted in exactly one place.

The owner portal, the clinic's own "my plan" page and every limit check need
the same numbers. If each counted for itself they would eventually disagree,
and the failure is a clinic told by one screen it has room for another doctor
and then refused by the check that counts differently (WIRE-002).

Callers must already be inside `tenant_context` for the tenant. Entering it
here would spread the decision of *when* to cross into a tenant, which
`platform_admin/permissions.py` deliberately keeps in one place.
"""

from django.db.models import Sum

from .entitlements import LIMITS, LimitReached, current_subscription, get_limit

MEGABYTE = 1024 * 1024

#: Arabic labels for the limits, for screens and refusal messages. The English
#: names in `entitlements.LIMITS` stay the identifiers.
LIMIT_LABELS = {
    "max_branches": "الفروع",
    "max_doctors": "الأطباء",
    "max_staff": "الموظفون",
    "max_patients": "المرضى",
    "max_storage_mb": "مساحة التخزين (ميجابايت)",
}


def doctor_count():
    from employees.models import Employee

    # "Doctor" is an employee type by name — the same rule Appointment.doctor's
    # limit_choices_to uses. It is defined here and nowhere else.
    return Employee.objects.filter(employee_type__name="Doctor").count()


def storage_bytes():
    from medical.models import MedicalAttachment

    # Attachments have no delete path (clinical retention, MED-011), so this
    # sum only grows and cannot drift. If a delete path is ever added, it
    # becomes a cached-count problem.
    return MedicalAttachment.objects.aggregate(total=Sum("size_bytes"))["total"] or 0


def usage_for(tenant):
    from branches.models import Branch
    from employees.models import Employee
    from patients.models import Patient

    return {
        "max_branches": Branch.objects.count(),
        "max_doctors": doctor_count(),
        "max_staff": Employee.objects.count(),
        # A self-registration awaiting review is not yet anyone's patient.
        "max_patients": Patient.objects.filter(needs_review=False).count(),
        # Rounded up, so a clinic at 0.2 MB shows 1 and not 0 — "nothing used"
        # would be false.
        "max_storage_mb": -(-storage_bytes() // MEGABYTE),
    }


def limits_table(tenant, subscription=None, usage=None):
    """Rows of used / allowed for screens. `allowed is None` means unlimited."""
    subscription = subscription if subscription is not None else current_subscription(tenant)
    usage = usage if usage is not None else usage_for(tenant)
    rows = []
    for field, label in LIMITS.items():
        allowed = getattr(subscription.plan, field) if subscription else 0
        used = usage.get(field)
        rows.append({
            "key": field,
            "label": label,
            "label_ar": LIMIT_LABELS.get(field, label),
            "used": used,
            "allowed": allowed,
            "unlimited": allowed is None,
            "over": allowed is not None and used is not None and used > allowed,
        })
    return rows


def check_storage(tenant, incoming_bytes):
    """Refuse an upload that would take the clinic past its storage allowance.

    Checked *before* the file is written: the incoming size is known from the
    upload itself, and refusing afterwards would leave the file on disk.
    """
    allowed_mb = get_limit(tenant, "max_storage_mb")
    if allowed_mb is None:
        return
    current = storage_bytes()
    if current + incoming_bytes > allowed_mb * MEGABYTE:
        raise LimitReached("max_storage_mb", allowed_mb, -(-current // MEGABYTE))


def limit_message(reached):
    """The refusal a clinic sees, in Arabic, naming what ran out."""
    label = LIMIT_LABELS.get(reached.limit, reached.limit)
    return (
        f"وصلت العيادة إلى حد الباقة في «{label}» ({reached.allowed}). "
        "تواصل معنا لترقية الباقة."
    )
