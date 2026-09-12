"""The platform's figures for the developer portal (docs/06 PLAT-005).

Two kinds, kept apart on purpose:

* **the platform's own business** — recurring revenue, invoices, collections,
  outstanding balances, discounts, signups and conversion, new and lost
  groups — from platform records (platform_admin/models.py, tenants), read
  directly;
* **what the groups do** — their appointments and the money they took this
  month — aggregated per group, each read inside that group's own
  `tenant_context` (row-level security still applies; totals only, no
  records).

Monthly recurring revenue counts groups whose status is active: a group's
negotiated price when it has one, else its plan's, as a monthly figure (a
yearly amount divided by twelve).
"""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from audit.models import AuditLog
from subscriptions.entitlements import current_subscription
from tenants.context import tenant_context
from tenants.models import Tenant

from .billing import add_months, money
from .models import CommercialTerms, PlatformInvoice, PlatformPayment, SignupRequest

ZERO = Decimal("0")


def monthly_value(tenant, terms):
    """What one group is worth a month, or None without a price."""
    if terms is not None and terms.custom_price is not None:
        price = Decimal(terms.custom_price)
        return price / 12 if terms.cycle == CommercialTerms.Cycle.YEARLY else price
    with tenant_context(tenant):
        subscription = current_subscription(tenant)
    if subscription is None:
        return None
    plan = subscription.plan
    price = Decimal(plan.price)
    if plan.billing_period == "yearly":
        return price / 12
    if plan.billing_period == "quarterly":
        return price / 3
    return price


def month_keys(months, today=None):
    today = today or timezone.now().date()
    first = date(today.year, today.month, 1)
    return [add_months(first, -offset) for offset in range(months - 1, -1, -1)]


def _series(queryset, date_field, keys, value=None):
    """{month: figure} for a queryset, over `keys` (first-of-month dates)."""
    rows = (
        queryset.filter(**{f"{date_field}__gte": keys[0]})
        .annotate(month=TruncMonth(date_field))
        .values("month")
        .annotate(figure=Sum(value) if value else Count("id"))
    )
    found = {}
    for row in rows:
        month = row["month"]
        month = month.date() if hasattr(month, "date") else month
        found[date(month.year, month.month, 1)] = row["figure"] or 0
    return [{"month": key.isoformat(), "value": str(money(found.get(key, 0))) if value else found.get(key, 0)}
            for key in keys]


def _group_activity(tenant, month_start):
    from appointments.models import Appointment
    from billing.models import Payment

    with tenant_context(tenant):
        appointments = Appointment.objects.filter(scheduled_date__date__gte=month_start).count()
        revenue = Payment.objects.filter(date__date__gte=month_start).aggregate(t=Sum("amount"))["t"] or ZERO
    return appointments, revenue


def report(months=12):
    months = max(1, min(int(months), 36))
    keys = month_keys(months)
    today = timezone.now().date()
    month_start = keys[-1]
    User = get_user_model()

    terms = {t.customer_id: t for t in CommercialTerms.objects.all()}
    tenants = list(Tenant.objects.order_by("name"))
    mrr = ZERO
    by_plan = {}
    groups = []
    for tenant in tenants:
        with tenant_context(tenant):
            subscription = current_subscription(tenant)
        plan_name = subscription.plan.name if subscription else "بدون باقة"
        by_plan[plan_name] = by_plan.get(plan_name, 0) + 1
        value = monthly_value(tenant, terms.get(tenant.pk)) if tenant.status == Tenant.Status.ACTIVE else None
        if value:
            mrr += value
        appointments, revenue = _group_activity(tenant, month_start)
        groups.append({
            "uuid": str(tenant.uuid), "name": tenant.name, "status": tenant.status,
            "status_label": tenant.get_status_display(), "plan": plan_name,
            "monthly_value": str(money(value)) if value else None,
            "appointments_this_month": appointments,
            "revenue_this_month": str(money(revenue)),
        })

    invoices = PlatformInvoice.objects.exclude(status=PlatformInvoice.Status.VOID)
    confirmed = PlatformPayment.objects.filter(status=PlatformPayment.Status.CONFIRMED)
    invoiced_total = invoices.aggregate(t=Sum("total"))["t"] or ZERO
    paid_total = confirmed.aggregate(t=Sum("amount"))["t"] or ZERO
    overdue = invoices.filter(status__in=["open", "partial"], due_on__lt=today)

    signups = SignupRequest.objects.all()
    handled = signups.exclude(status=SignupRequest.Status.PENDING).count()
    approved = signups.filter(status=SignupRequest.Status.APPROVED).count()

    lost = AuditLog.objects.filter(tenant__isnull=False, description__startswith="[platform] tenant status") \
        .filter(description__regex=r"-> (suspended|cancelled)$")

    accounts = User.objects.filter(tenant__isnull=False, is_active=True)
    return {
        "months": [key.isoformat() for key in keys],
        "totals": {
            "mrr": str(money(mrr)),
            "arr": str(money(mrr * 12)),
            "groups": len(tenants),
            "active_groups": sum(1 for t in tenants if t.status == Tenant.Status.ACTIVE),
            "trial_groups": sum(1 for t in tenants if t.status == Tenant.Status.TRIAL),
            "lost_groups": sum(1 for t in tenants if t.status in (Tenant.Status.SUSPENDED, Tenant.Status.CANCELLED)),
            "invoiced": str(money(invoiced_total)),
            "collected": str(money(paid_total)),
            "outstanding": str(money(invoiced_total - paid_total)),
            "overdue_invoices": overdue.count(),
            "discounts_given": str(money(invoices.aggregate(t=Sum("discount_amount"))["t"] or ZERO)),
            "signups_pending": signups.filter(status=SignupRequest.Status.PENDING).count(),
            "conversion_percent": round(100 * approved / handled) if handled else None,
            "accounts": accounts.count(),
            "active_7_days": accounts.filter(last_seen_at__date__gte=today - timedelta(days=7)).count(),
            "active_30_days": accounts.filter(last_seen_at__date__gte=today - timedelta(days=30)).count(),
            "appointments_this_month": sum(g["appointments_this_month"] for g in groups),
            "clinic_revenue_this_month": str(money(sum(Decimal(g["revenue_this_month"]) for g in groups))),
        },
        "series": {
            "invoiced": _series(invoices, "period_start", keys, "total"),
            "collected": _series(confirmed, "paid_at", keys, "amount"),
            "discounts": _series(invoices, "period_start", keys, "discount_amount"),
            "signups": _series(signups, "created_at", keys),
            "new_groups": _series(Tenant.objects.all(), "created_at", keys),
            "lost_groups": _series(lost, "created_at", keys),
        },
        "by_plan": [{"plan": name, "groups": count} for name, count in sorted(by_plan.items(), key=lambda x: -x[1])],
        "groups": sorted(groups, key=lambda g: Decimal(g["revenue_this_month"]), reverse=True),
    }
