import uuid

from django.db import models


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
