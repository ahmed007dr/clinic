import django.db.models.deletion
from django.db import migrations, models


def backfill_tenant(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    tenant = Tenant.objects.order_by("id").first()
    if tenant is None:
        return
    apps.get_model("patients", "Patient").objects.filter(tenant__isnull=True).update(tenant=tenant)


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0002_create_default_tenant"),
        ("patients", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="patient",
            name="tenant",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="tenants.tenant",
            ),
        ),
        migrations.RunPython(backfill_tenant, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="patient",
            name="tenant",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="tenants.tenant",
            ),
        ),
    ]
