# accounts/models.py
from django.db import models
from django.contrib.auth.models import AbstractUser
from branches.models import Branch
from tenants.models import Tenant, TenantOwnedModel

class ClinicRole(TenantOwnedModel):
    name = models.CharField(max_length=50)
    description = models.TextField(blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="uniq_clinicrole_name_per_tenant")
        ]

    def __str__(self):
        return self.name

class User(AbstractUser):
    # Null only for platform staff (SaaS operators), who legitimately span tenants.
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="+", null=True, blank=True)
    clinic_code = models.CharField(max_length=20)
    role = models.ForeignKey(ClinicRole, on_delete=models.SET_NULL, null=True, blank=True)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True)  
    def __str__(self):
        return f"{self.username} ({self.role})"

    @property
    def unread_notifications(self):
        try:
            return self.notifications.filter(is_read=False)
        except Exception:
            return []
