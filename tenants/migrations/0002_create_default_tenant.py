from django.conf import settings
from django.db import migrations
from django.utils.text import slugify


def create_default_tenant(apps, schema_editor):
    """Tenant #1 is the clinic already using this system.

    Everything existing gets backfilled onto it by each app's 0002_add_tenant,
    so the system keeps behaving exactly as it did before multi-tenancy.
    """
    Tenant = apps.get_model("tenants", "Tenant")
    if Tenant.objects.exists():
        return

    name = getattr(settings, "CLINIC_NAME", None) or "Default Clinic"
    Tenant.objects.create(
        name=name,
        slug=slugify(name) or "default",
        status="active",
    )


def remove_default_tenant(apps, schema_editor):
    # Intentionally a no-op: rows backfilled onto this tenant would be orphaned,
    # and PROTECT would block the delete anyway.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_default_tenant, remove_default_tenant),
    ]
