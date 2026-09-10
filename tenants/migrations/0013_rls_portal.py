"""Extend the isolation policies to the patient portal's tables.

`portal.PatientAccount`, `PortalInvitation` and `PortalSession` are tenant-owned,
so the derivation picks them up like every other model with a non-nullable
tenant. They matter more than most: they hold the hashed credentials a patient
signs in with, and a portal request looks them up only after binding the
clinic from the URL — so without a policy, the one thing standing between a
token and another clinic's accounts would be application code.
"""

from django.db import migrations

from tenants.rls import apply_tenant_policies, drop_tenant_policies


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0012_tenant_portal_show_diagnosis"),
        ("portal", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(apply_tenant_policies, drop_tenant_policies),
    ]
