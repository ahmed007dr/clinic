"""Extend the isolation policies to `billing.CashShift`.

A shift carries a clinic's takings per person per day; the derivation in
tenants.rls picks it up like every other model with a non-nullable tenant.
"""

from django.db import migrations

from tenants.rls import apply_tenant_policies, drop_tenant_policies


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0015_tenant_portal_self_registration"),
        ("billing", "0007_cash_shifts"),
    ]

    operations = [
        migrations.RunPython(apply_tenant_policies, drop_tenant_policies),
    ]
