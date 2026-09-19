"""Extend the isolation policies to branch services.

`services.BranchService` is tenant-owned (which services each clinic of a group
offers); another group must never read it. Picked up by the derivation in
tenants.rls like every other such model.
"""

from django.db import migrations

from tenants.rls import apply_tenant_policies, drop_tenant_policies


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0022_rls_portal_verification"),
        ("services", "0008_backfill_branch_services"),
    ]

    operations = [
        migrations.RunPython(apply_tenant_policies, drop_tenant_policies),
    ]
