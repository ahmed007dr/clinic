from django.apps import AppConfig
from django.db.models.signals import post_migrate
from django.db.utils import OperationalError, ProgrammingError


def _is_missing_table(exc):
    """The one condition this hook is allowed to ignore: a partial migrate,
    where the accounts/employees tables do not exist yet. PostgreSQL says
    "does not exist", SQLite says "no such table"."""
    message = str(exc).lower()
    return "does not exist" in message or "no such table" in message


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
    except (OperationalError, ProgrammingError) as exc:
        if _is_missing_table(exc):
            return  # the next migrate catches up
        # Everything else is a real failure and must be loud. An RLS policy
        # rejecting the write raises ProgrammingError too, and swallowing that
        # left tenants with no Admin role and no Doctor type — unusable, with
        # nothing in the output to say so.
        raise


class TenantsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tenants"

    def ready(self):
        post_migrate.connect(ensure_tenant_defaults, sender=self)
