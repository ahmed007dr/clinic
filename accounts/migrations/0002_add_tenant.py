import django.db.models.deletion
from django.db import migrations, models


def backfill_tenant(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    tenant = Tenant.objects.order_by("id").first()
    if tenant is None:
        return
    for model_name in ("ClinicRole", "User"):
        apps.get_model("accounts", model_name).objects.filter(tenant__isnull=True).update(tenant=tenant)


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0002_create_default_tenant"),
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="clinicrole",
            name="tenant",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="tenants.tenant",
            ),
        ),
        # User.tenant stays nullable in its final form — null means platform staff.
        migrations.AddField(
            model_name="user",
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
        migrations.AlterField(
            model_name="clinicrole",
            name="tenant",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="tenants.tenant",
            ),
        ),
    ]
