"""What the platform operator sees across clinics (developer portal, phase 1).

Two kinds of data, read two ways:

* **Accounts** (`accounts.User`) are not tenant-owned — platform operators live
  there too — so who is online, when each account was last seen, and who owns
  each group are ordinary queries across the whole table.
* **Clinic records** (branches, employees, patients) are tenant-owned and
  behind row-level security, so they are read one group at a time inside that
  group's `tenant_context` — the rule platform_admin/permissions.py sets.

Only counts and account metadata leave this module; nothing clinical.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, Max, Q
from django.utils import timezone

from accounts.roles import ADMIN, DOCTOR, OWNER, RECEPTION
from subscriptions.entitlements import current_subscription
from subscriptions.usage import limits_table, usage_for
from tenants.context import tenant_context
from tenants.models import Tenant

User = get_user_model()

#: Seen within this long counts as "online now".
ONLINE_WINDOW = timedelta(minutes=5)
#: A group with no account active for this long is flagged inactive.
INACTIVE_AFTER = timedelta(days=7)
#: Share of a plan limit at which a group is flagged as near it.
NEAR_LIMIT = 0.8


def online_cutoff():
    return timezone.now() - ONLINE_WINDOW


def account_row(user, cutoff=None):
    cutoff = cutoff or online_cutoff()
    return {
        "uuid": str(user.uuid),
        "username": user.username,
        "email": user.email,
        "name": f"{user.first_name} {user.last_name}".strip(),
        "role": getattr(user.role, "name", None),
        "branch": getattr(user.branch, "name", None),
        "is_active": user.is_active,
        "last_seen_at": user.last_seen_at,
        "last_login": user.last_login,
        "online": bool(user.is_active and user.last_seen_at and user.last_seen_at >= cutoff),
    }


def _limit_flags(rows):
    near, over = [], []
    for row in rows:
        allowed, used = row["allowed"], row["used"]
        if allowed in (None, 0) or used is None:
            continue
        if used > allowed:
            over.append(row["label_ar"])
        elif used >= allowed * NEAR_LIMIT:
            near.append(row["label_ar"])
    return near, over


def group_row(tenant, cutoff=None):
    """One owner group: plan, people, activity and limits."""
    cutoff = cutoff or online_cutoff()
    accounts = User.objects.filter(tenant=tenant)
    people = accounts.aggregate(
        users=Count("id", filter=Q(is_active=True)),
        online=Count("id", filter=Q(is_active=True, last_seen_at__gte=cutoff)),
        last_seen=Max("last_seen_at"),
        doctor_accounts=Count("id", filter=Q(is_active=True, role__name=DOCTOR)),
        staff_accounts=Count("id", filter=Q(is_active=True, role__name__in=[ADMIN, RECEPTION])),
    )
    owners = [
        {"name": u.username, "email": u.email}
        for u in accounts.filter(role__name=OWNER, is_active=True).order_by("username")
    ]
    with tenant_context(tenant):
        subscription = current_subscription(tenant)
        usage = usage_for(tenant)
        near, over = _limit_flags(limits_table(tenant, subscription, usage))
    last_seen = people["last_seen"]
    return {
        "uuid": str(tenant.uuid),
        "name": tenant.name,
        "slug": tenant.slug,
        "status": tenant.status,
        "status_label": tenant.get_status_display(),
        "created_at": tenant.created_at,
        "plan": subscription.plan.name if subscription else None,
        "subscription_status": subscription.get_status_display() if subscription else None,
        "owners": owners,
        "branches": usage["max_branches"],
        "doctors": usage["max_doctors"],
        "employees": usage["max_staff"],
        "patients": usage["max_patients"],
        "storage_mb": usage["max_storage_mb"],
        "accounts": people["users"],
        "doctor_accounts": people["doctor_accounts"],
        "staff_accounts": people["staff_accounts"],
        "online": people["online"],
        "last_seen_at": last_seen,
        "inactive": last_seen is None or last_seen < timezone.now() - INACTIVE_AFTER,
        "near_limits": near,
        "over_limits": over,
    }


def overview():
    """Every group's row, and platform-wide totals built from them."""
    cutoff = online_cutoff()
    rows = [group_row(tenant, cutoff) for tenant in Tenant.objects.order_by("name")]
    by_status = {}
    for row in rows:
        by_status[row["status"]] = by_status.get(row["status"], 0) + 1
    day_ago = timezone.now() - timedelta(days=1)
    clinic_accounts = User.objects.filter(tenant__isnull=False, is_active=True)
    totals = {
        "groups": len(rows),
        "by_status": by_status,
        "branches": sum(r["branches"] for r in rows),
        "doctors": sum(r["doctors"] for r in rows),
        "employees": sum(r["employees"] for r in rows),
        "patients": sum(r["patients"] for r in rows),
        "accounts": clinic_accounts.count(),
        "online": clinic_accounts.filter(last_seen_at__gte=cutoff).count(),
        "active_today": clinic_accounts.filter(last_seen_at__gte=day_ago).count(),
        "inactive_groups": sum(1 for r in rows if r["inactive"]),
        "near_limit_groups": sum(1 for r in rows if r["near_limits"] or r["over_limits"]),
    }
    return {"totals": totals, "groups": rows}


def people_of(tenant):
    """Per clinic (branch) of one group: doctors, employees and accounts —
    and every account with its last activity."""
    from branches.models import Branch
    from employees.models import Employee

    cutoff = online_cutoff()
    accounts = list(
        User.objects.filter(tenant=tenant).select_related("role", "branch").order_by("-last_seen_at", "username")
    )
    with tenant_context(tenant):
        branches = list(Branch.all_objects.filter(tenant=tenant).order_by("name"))
        employees = (
            Employee.all_objects.filter(tenant=tenant)
            .values("branch_id")
            .annotate(
                doctors=Count("id", filter=Q(employee_type__name=DOCTOR)),
                total=Count("id"),
            )
        )
        per_branch = {row["branch_id"]: row for row in employees}
    rows = []
    for branch in branches:
        mine = [a for a in accounts if a.branch_id == branch.pk and a.is_active]
        counts = per_branch.get(branch.pk, {})
        rows.append({
            "uuid": str(branch.uuid),
            "name": branch.name,
            "is_active": branch.is_active,
            "doctors": counts.get("doctors", 0),
            "employees": counts.get("total", 0),
            "accounts": len(mine),
            "online": sum(1 for a in mine if a.last_seen_at and a.last_seen_at >= cutoff),
        })
    return {
        "branches": rows,
        "accounts": [account_row(a, cutoff) for a in accounts],
    }


def online_now():
    """Everyone signed in and active in the last few minutes, across groups."""
    cutoff = online_cutoff()
    users = (
        User.objects.filter(is_active=True, last_seen_at__gte=cutoff)
        .select_related("role", "branch", "tenant")
        .order_by("-last_seen_at")
    )
    return [
        {
            **account_row(user, cutoff),
            "group": getattr(user.tenant, "name", None),
            "group_uuid": str(user.tenant.uuid) if user.tenant_id else None,
            "platform": user.is_platform_staff,
        }
        for user in users
    ]
