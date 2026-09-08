# accounts/apps.py
from django.apps import AppConfig
from django.db.models.signals import post_migrate

def ensure_default_roles(sender, **kwargs):
    """Roles are tenant-owned, so seed them per tenant.

    Interim: TENANT-008 moves this into tenant provisioning, where it belongs.
    Note ClinicRole.name is still globally unique until TENANT-003 converts it
    to (tenant, name) — so this only works while a single tenant exists.
    """
    from accounts.models import ClinicRole
    from tenants.models import Tenant

    for tenant in Tenant.objects.all():
        ClinicRole.objects.get_or_create(
            tenant=tenant, name="Admin", defaults={"description": "System administrator"}
        )
        ClinicRole.objects.get_or_create(
            tenant=tenant, name="Reception", defaults={"description": "Reception staff"}
        )

class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    def ready(self):
        post_migrate.connect(ensure_default_roles, sender=self)
