"""Extend the isolation policies to doctor contracts and commissions.

`billing.DoctorServiceRate` holds each doctor's prices and shares;
`billing.DoctorCommission` what each doctor is owed. Both tenant-owned, picked
up by the derivation in tenants.rls like every other such model.
"""

from django.db import migrations

from tenants.rls import apply_tenant_policies, drop_tenant_policies


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0016_rls_cash_shifts"),
        ("billing", "0008_doctor_contracts_commissions"),
    ]

    operations = [
        migrations.RunPython(apply_tenant_policies, drop_tenant_policies),
    ]
