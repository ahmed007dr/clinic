import uuid

from django.db import models, transaction


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


class TenantOwnedModel(models.Model):
    """Base for every model whose rows belong to exactly one tenant.

    PROTECT, never CASCADE: removing a tenant must not silently delete medical
    or financial records — offboarding is a deliberate export-then-delete flow.
    related_name='+' because 15 models point here and none need a reverse accessor.
    """

    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="+")

    class Meta:
        abstract = True


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
