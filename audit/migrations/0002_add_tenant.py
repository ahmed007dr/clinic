import django.db.models.deletion
from django.db import migrations, models


def backfill_tenant(apps, schema_editor):
    """Existing audit rows all belong to the single pre-existing clinic."""
    Tenant = apps.get_model("tenants", "Tenant")
    tenant = Tenant.objects.order_by("id").first()
    if tenant is None:
        return
    apps.get_model("audit", "AuditLog").objects.filter(tenant__isnull=True).update(tenant=tenant)


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0002_create_default_tenant"),
        ("audit", "0001_initial"),
    ]

    operations = [
        # Stays nullable: platform-level events (creating a Tenant, platform
        # staff actions) legitimately belong to no tenant.
        migrations.AddField(
            model_name="auditlog",
            name="tenant",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="tenants.tenant",
            ),
        ),
        migrations.RunPython(backfill_tenant, migrations.RunPython.noop),
    ]
