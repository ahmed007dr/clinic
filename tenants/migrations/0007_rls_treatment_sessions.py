"""Extend the isolation policies to medical.TreatmentSession.

The set of protected tables is derived from the models (tenants/rls.py), so
this migration adds no list of its own — it simply reapplies, and the new
tenant-owned table is included because it has a non-nullable `tenant`.

This is the standard closing step for any migration that introduces a
tenant-owned model. `tenants/test_rls.py` derives its expectations the same
way, so omitting it fails the suite rather than shipping an unprotected table.
"""

from django.db import migrations

from tenants.rls import apply_tenant_policies, drop_tenant_policies


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0006_rls_covers_new_tenant_tables"),
        ("medical", "0004_treatmentsession_and_more"),
    ]

    operations = [
        migrations.RunPython(apply_tenant_policies, drop_tenant_policies),
    ]
