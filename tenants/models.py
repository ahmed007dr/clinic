import uuid

from django.db import models, transaction

from .context import get_current_tenant


class Tenant(models.Model):
    """A paying customer — one clinic business, owning one or more Branches."""

    class Status(models.TextChoices):
        TRIAL = "trial", "تجريبي"
        ACTIVE = "active", "نشط"
        SUSPENDED = "suspended", "موقوف"
        CANCELLED = "cancelled", "ملغي"

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=50, unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TRIAL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "مستأجر"
        verbose_name_plural = "المستأجرون"

    def __str__(self):
        return self.name

    @property
    def is_usable(self):
        return self.status in {self.Status.TRIAL, self.Status.ACTIVE}


class TenantManager(models.Manager):
    """Scopes every read to the tenant in context, and fails closed.

    No tenant in context returns nothing rather than everything: the direction
    a mistake falls matters more than whether one happens. Use `all_objects`
    where crossing tenants is genuinely intended (platform staff, scheduled
    jobs that loop over tenants, migrations).
    """

    def get_queryset(self):
        queryset = super().get_queryset()
        tenant = get_current_tenant()
        if tenant is None:
            return queryset.none()
        return queryset.filter(tenant=tenant)


class TenantOwnedModel(models.Model):
    """Base for every model whose rows belong to exactly one tenant.

    PROTECT, never CASCADE: removing a tenant must not silently delete medical
    or financial records — offboarding is a deliberate export-then-delete flow.
    related_name='+' because 15 models point here and none need a reverse accessor.
    """

    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="+")

    # Declared first, so _default_manager (admin, ModelForm querysets) is the
    # safe one. base_manager_name keeps _base_manager unfiltered — Django uses
    # it to follow foreign keys, and filtering that breaks related lookups.
    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True
        base_manager_name = "all_objects"


class SerialCounter(models.Model):
    """Per-tenant, per-day sequence behind the YYYYMMDD-NNN serial numbers.

    Replaces counting matching rows on every insert, which was O(n) and grew
    permanently slower, raced under concurrency, and — once more than one
    tenant shares a table — handed each tenant numbers that disclosed the
    others' daily volume.
    """

    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="+")
    scope = models.CharField(max_length=40)
    date = models.DateField()
    last_value = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "scope", "date"], name="uniq_serial_counter_per_scope_day"
            )
        ]

    def __str__(self):
        return f"{self.scope} {self.date} -> {self.last_value}"

    @classmethod
    def next_serial(cls, tenant_id, scope, date):
        """Reserve and format the next serial for this tenant/scope/day.

        select_for_update makes this genuinely atomic on PostgreSQL; SQLite
        serialises writers anyway. A failed insert afterwards leaves a gap,
        which is fine — these are display identifiers, not a ledger sequence.
        """
        with transaction.atomic():
            counter, _ = cls.objects.select_for_update().get_or_create(
                tenant_id=tenant_id, scope=scope, date=date
            )
            counter.last_value += 1
            counter.save(update_fields=["last_value"])
        return f"{date.strftime('%Y%m%d')}-{counter.last_value:03d}"
