"""Extend the isolation policies to medical.LabResult.

The protected set is derived from the models (tenants/rls.py); this reapplies
it, and the new tenant-owned table is included because it has a non-nullable
`tenant`. Standard closing step for any migration adding a tenant-owned model.
"""

from django.db import migrations

from tenants.rls import apply_tenant_policies, drop_tenant_policies


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0008_rls_procedures"),
        ("medical", "0006_labresult"),
    ]

    operations = [
        migrations.RunPython(apply_tenant_policies, drop_tenant_policies),
    ]
