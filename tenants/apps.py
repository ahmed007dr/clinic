from django.apps import AppConfig
from django.db.models.signals import post_migrate
from django.db.utils import OperationalError, ProgrammingError


def ensure_tenant_defaults(sender, **kwargs):
    """Backstop for tenants that predate provisioning, or that a migration created.

    New tenants get seeded by tenants.provisioning.create_tenant; this only
    catches up anything that missed it.
    """
    from .models import Tenant
    from .provisioning import provision_tenant_defaults

    try:
        for tenant in Tenant.objects.all():
            provision_tenant_defaults(tenant)
    except (OperationalError, ProgrammingError):
        # Tables for accounts/employees not created yet (partial migrate).
        return


class TenantsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tenants"

    def ready(self):
        post_migrate.connect(ensure_tenant_defaults, sender=self)
