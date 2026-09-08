"""Reapply the isolation policies, this time derived from the models.

tenants.0005 worked from a hand-written list of tables. Adding a tenant-owned
model since then (medical.TreatmentPlan) left that list stale, and a stale list
is a table with no policy and nothing to say so.

This migration recomputes the set from the model registry — see tenants/rls.py
— and reapplies it. It is idempotent: policies are dropped and recreated, so
the 19 tables already covered are unaffected and the new one is added.

Every later migration that introduces a tenant-owned model should end with the
same RunPython pair. `tenants/test_rls.py` derives its expectations the same
way, so forgetting fails the suite rather than shipping an unprotected table.
"""

from django.db import migrations

from tenants.rls import apply_tenant_policies, drop_tenant_policies


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0005_row_level_security"),
        ("medical", "0003_treatmentplan"),
    ]

    operations = [
        migrations.RunPython(apply_tenant_policies, drop_tenant_policies),
    ]
