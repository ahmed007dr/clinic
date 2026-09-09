"""Extend the isolation policies to medical.Procedure.

The protected set is derived from the models (tenants/rls.py), so this adds no
list of its own — it reapplies, and the new tenant-owned table is included
because it has a non-nullable `tenant`.

This is the standard closing step for any migration introducing a tenant-owned
model; `tenants/test_rls.py` derives its expectations the same way, so omitting
it fails the suite rather than shipping an unprotected table.
"""

from django.db import migrations

from tenants.rls import apply_tenant_policies, drop_tenant_policies


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0007_rls_treatment_sessions"),
        ("medical", "0005_procedure"),
    ]

    operations = [
        migrations.RunPython(apply_tenant_policies, drop_tenant_policies),
    ]
