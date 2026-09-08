import django.db.models.deletion
from django.db import migrations, models

MODELS = ("PaymentMethod", "Payment", "ExpenseCategory", "Expense")


def backfill_tenant(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    tenant = Tenant.objects.order_by("id").first()
    if tenant is None:
        return
    for model_name in MODELS:
        apps.get_model("billing", model_name).objects.filter(tenant__isnull=True).update(tenant=tenant)


def _nullable():
    return models.ForeignKey(
        null=True,
        on_delete=django.db.models.deletion.PROTECT,
        related_name="+",
        to="tenants.tenant",
    )


def _required():
    return models.ForeignKey(
        on_delete=django.db.models.deletion.PROTECT,
        related_name="+",
        to="tenants.tenant",
    )


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0002_create_default_tenant"),
        ("billing", "0001_initial"),
    ]

    operations = (
        [migrations.AddField(model_name=m.lower(), name="tenant", field=_nullable()) for m in MODELS]
        + [migrations.RunPython(backfill_tenant, migrations.RunPython.noop)]
        + [migrations.AlterField(model_name=m.lower(), name="tenant", field=_required()) for m in MODELS]
    )
