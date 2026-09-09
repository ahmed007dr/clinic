"""What a tenant is allowed to do — doc/readme.md §11, §84.

§11 gives plans two kinds of allowance and they behave differently, so they are
modelled differently:

* **Limits** are counts — branches, doctors, staff, patients, storage. They are
  columns on the plan, because they are a fixed short list from the spec and
  keeping them as columns makes "which tenants are near their patient limit"
  an ordinary query rather than a JSON scan.
* **Features** are on/off — WhatsApp, online payments, analytics, AI, packages.
  §11 ends the list with "other features" and §84 wants them per plan *and* per
  tenant, so a fixed set of columns would mean a migration every time sales
  invents a package. They live in JSON, validated against the registry below so
  a typo is an error rather than a silently absent feature.

The registry is the point of this module. `features["whatsap"]` returning False
would read exactly like a disabled feature, and nobody would find it until a
customer complained; validating keys turns that into a loud failure at save
time.

**Resolution order** is plan, then tenant override. §11 allows "custom
contracts", which in practice means one clinic gets something its tier does not
include, and an override on the subscription expresses that without inventing a
private plan for every negotiation.

Everything here fails closed. An unknown feature is off, a tenant with no
subscription gets nothing, and a limit that cannot be resolved blocks rather
than allows — the cost of a wrongly blocked action is an error message, while
the cost of a wrongly allowed one is a customer using what they have not paid
for, or a tenant exceeding capacity nobody planned for.
"""

from django.core.exceptions import ValidationError

# key -> (label, default when no plan grants it)
FEATURES = {
    "whatsapp": ("WhatsApp notifications", False),
    "online_payments": ("Online payments", False),
    "advanced_analytics": ("Advanced analytics", False),
    "ai": ("AI features", False),
    "packages": ("Treatment packages", False),
    "reports": ("Scheduled reports", True),
}

# Limit field name -> label. Stored as columns on Plan; None means unlimited.
LIMITS = {
    "max_branches": "Branches",
    "max_doctors": "Doctors",
    "max_staff": "Staff",
    "max_patients": "Patients",
    "max_storage_mb": "Storage (MB)",
}


class FeatureUnavailable(Exception):
    """Raised when a tenant's plan does not include a feature. Carries the key
    so a view can say which one without inventing its own message."""

    def __init__(self, feature):
        self.feature = feature
        super().__init__(f"feature not available on this plan: {feature}")


class LimitReached(Exception):
    """Raised when an action would exceed a plan limit."""

    def __init__(self, limit, allowed, current):
        self.limit = limit
        self.allowed = allowed
        self.current = current
        super().__init__(f"{limit} limit reached: {current}/{allowed}")


def validate_feature_keys(values):
    """Used by Plan and Subscription clean(). Unknown keys are rejected rather
    than ignored, because an ignored key is a feature someone believes they
    granted."""
    if not isinstance(values, dict):
        raise ValidationError("Features must be a mapping of key to true/false.")
    unknown = sorted(set(values) - set(FEATURES))
    if unknown:
        known = ", ".join(sorted(FEATURES))
        raise ValidationError(
            f"Unknown feature key(s): {', '.join(unknown)}. Known keys: {known}"
        )
    for key, value in values.items():
        if not isinstance(value, bool):
            raise ValidationError(f"Feature '{key}' must be true or false.")


def default_features():
    return {key: default for key, (_, default) in FEATURES.items()}


def current_subscription(tenant):
    """The subscription a tenant is currently being served under, or None.

    Imported lazily to keep this module importable from models.py without a
    circular import.
    """
    from .models import Subscription

    if tenant is None:
        return None
    return (
        Subscription.all_objects.filter(tenant=tenant)
        .select_related("plan")
        .order_by("-started_on", "-id")
        .filter(status=Subscription.Status.ACTIVE)
        .first()
    )


def resolve_features(tenant):
    """Effective on/off state for every known feature.

    A tenant with no active subscription gets the registry defaults, which are
    off for everything chargeable. That is the fail-closed case: an unpaid or
    lapsed tenant keeps working for the basics and loses the extras.
    """
    resolved = default_features()
    subscription = current_subscription(tenant)
    if subscription is None:
        return resolved
    resolved.update(subscription.plan.features or {})
    # Per-tenant overrides win: §11's "custom contracts" are one clinic getting
    # something its tier does not include, without inventing a private plan.
    resolved.update(subscription.feature_overrides or {})
    return resolved


def has_feature(tenant, feature):
    if feature not in FEATURES:
        # Not a silent False: asking about a feature that does not exist is a
        # programming error, and returning False would hide it forever.
        raise KeyError(f"unknown feature: {feature}")
    return bool(resolve_features(tenant).get(feature, False))


def require_feature(tenant, feature):
    if not has_feature(tenant, feature):
        raise FeatureUnavailable(feature)


def get_limit(tenant, limit):
    """The tenant's allowance for a limit, or None for unlimited.

    No subscription means no allowance — 0, not unlimited. Treating "unknown"
    as "unrestricted" is the mistake that lets a lapsed tenant grow without
    bound.
    """
    if limit not in LIMITS:
        raise KeyError(f"unknown limit: {limit}")
    subscription = current_subscription(tenant)
    if subscription is None:
        return 0
    return getattr(subscription.plan, limit)


def check_limit(tenant, limit, current_count):
    """Raise if adding one more would exceed the plan.

    Takes the count rather than computing it: the caller already has a scoped
    queryset, and counting here would need to know each model's tenant and
    branch scoping rules.
    """
    allowed = get_limit(tenant, limit)
    if allowed is None:
        return
    if current_count >= allowed:
        raise LimitReached(limit, allowed, current_count)
