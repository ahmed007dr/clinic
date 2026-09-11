"""Plans and subscriptions — doc/readme.md §10, §11, §84.

Two models with deliberately different ownership, and the difference matters:

* `Plan` is **platform-level**. It is the catalogue every tenant chooses from,
  so it carries no tenant foreign key and is therefore not picked up by the
  row-level security policy set (see tenants/rls.py, which derives membership
  from having a non-nullable `tenant`). A plan is not anybody's private data.
* `Subscription` **is** tenant-owned and so is RLS-protected like every other
  tenant table. A clinic can see what it is paying for; it cannot see anyone
  else's terms. The consequence is that genuinely cross-tenant billing queries
  ("subscription revenue", §47) need the per-tenant loop or the deferred
  privileged read path — the same trade already accepted for platform admin.
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from tenants.models import TenantOwnedModel

from .entitlements import LIMITS, default_features, validate_feature_keys


class Plan(models.Model):
    """A tier in the catalogue: Basic, Professional, Enterprise, Custom (§11).

    Limits are columns and features are JSON, for the reasons set out in
    entitlements.py — the short answer is that limits are a fixed list worth
    querying and features are an open-ended list that must not need a migration
    every time one is added.

    `None` on a limit means unlimited, which is why they are nullable rather
    than defaulting to a large number: "unlimited" and "a million" are different
    statements, and only one of them survives a customer with a million patients.
    """

    class BillingPeriod(models.TextChoices):
        MONTHLY = "monthly", "شهري"
        QUARTERLY = "quarterly", "ربع سنوي"
        YEARLY = "yearly", "سنوي"
        # §11: "Custom contracts" — the period is whatever was negotiated, and
        # the dates on the subscription are then the source of truth.
        CUSTOM = "custom", "عقد مخصص"

    code = models.SlugField(max_length=50, unique=True, verbose_name="الرمز")
    name = models.CharField(max_length=100, verbose_name="اسم الباقة")
    description = models.TextField(blank=True, verbose_name="الوصف")

    billing_period = models.CharField(
        max_length=20, choices=BillingPeriod.choices, default=BillingPeriod.MONTHLY,
        verbose_name="دورة الفوترة",
    )
    price = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, verbose_name="السعر"
    )
    currency = models.CharField(max_length=3, default="EGP", verbose_name="العملة")

    # null = unlimited, for every one of these.
    max_branches = models.PositiveIntegerField(null=True, blank=True)
    max_doctors = models.PositiveIntegerField(null=True, blank=True)
    max_staff = models.PositiveIntegerField(null=True, blank=True)
    max_patients = models.PositiveIntegerField(null=True, blank=True)
    max_storage_mb = models.PositiveIntegerField(null=True, blank=True)

    features = models.JSONField(default=default_features, blank=True)

    is_active = models.BooleanField(
        default=True,
        help_text="Inactive plans keep serving existing subscribers but are not offered.",
    )
    is_public = models.BooleanField(
        default=True,
        help_text="Custom contracts are not shown in the catalogue.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["price", "name"]
        verbose_name = "باقة"
        verbose_name_plural = "الباقات"

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        validate_feature_keys(self.features or {})

    def limit_display(self, limit):
        value = getattr(self, limit)
        return "غير محدود" if value is None else value

    @property
    def limits(self):
        return {name: getattr(self, name) for name in LIMITS}


class Subscription(TenantOwnedModel):
    """What a tenant is currently paying for.

    Kept as a history rather than a single field on Tenant: a clinic upgrades,
    downgrades, lapses and renews, and billing needs to be able to say what the
    terms were in March. `entitlements.current_subscription` picks the active
    one; the rest are the record.

    `feature_overrides` is how §11's custom contracts work without a private
    plan per negotiation — the plan says what the tier includes, the override
    says what this clinic additionally agreed.
    """

    class Status(models.TextChoices):
        TRIAL = "trial", "تجريبي"
        ACTIVE = "active", "نشط"
        PAST_DUE = "past_due", "متأخر السداد"
        CANCELLED = "cancelled", "ملغي"
        EXPIRED = "expired", "منتهي"

    plan = models.ForeignKey(
        Plan, on_delete=models.PROTECT, related_name="subscriptions",
        verbose_name="الباقة",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.TRIAL,
        verbose_name="الحالة",
    )

    started_on = models.DateField(default=timezone.now, verbose_name="تاريخ البدء")
    # null = open-ended, which is what a monthly subscription that keeps
    # renewing looks like until somebody cancels it.
    ends_on = models.DateField(null=True, blank=True, verbose_name="تاريخ الانتهاء")
    trial_ends_on = models.DateField(null=True, blank=True, verbose_name="نهاية التجربة")

    feature_overrides = models.JSONField(
        default=dict, blank=True,
        help_text="Per-tenant grants beyond the plan — §11 custom contracts.",
    )
    # The same for limits, set from the developer portal: {limit: number or
    # None}. A key present wins over the plan (None = unlimited); a key
    # absent means the plan's own allowance.
    limit_overrides = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True, verbose_name="ملاحظات")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["-started_on", "-id"]
        constraints = [
            # A tenant can have a history, but only one live subscription at a
            # time — two actives would make "which plan is this?" ambiguous, and
            # entitlement resolution would silently pick whichever sorted first.
            models.UniqueConstraint(
                fields=["tenant"],
                condition=models.Q(status="active"),
                name="one_active_subscription_per_tenant",
            ),
            models.CheckConstraint(
                condition=models.Q(ends_on__isnull=True)
                | models.Q(ends_on__gte=models.F("started_on")),
                name="subscription_ends_after_it_starts",
            ),
        ]
        verbose_name = "اشتراك"
        verbose_name_plural = "الاشتراكات"

    def __str__(self):
        return f"{self.tenant} — {self.plan}"

    def clean(self):
        super().clean()
        validate_feature_keys(self.feature_overrides or {})

    @property
    def is_live(self):
        return self.status == self.Status.ACTIVE

    @property
    def in_trial(self):
        return (
            self.status == self.Status.TRIAL
            and self.trial_ends_on is not None
            and self.trial_ends_on >= timezone.now().date()
        )

    def allowed(self, limit):
        """This subscription's allowance for `limit` — the developer's
        override if there is one, else the plan's. None = unlimited."""
        overrides = self.limit_overrides or {}
        if limit in overrides:
            return overrides[limit]
        return getattr(self.plan, limit)
