"""Extend the isolation policies to portal verifications.

`portal.PortalVerification` is tenant-owned and holds what a person typed while
creating a portal account, plus a live one-time code (hashed); another clinic
must never read it. Picked up by the derivation in tenants.rls like every other
such model.
"""

from django.db import migrations

from tenants.rls import apply_tenant_policies, drop_tenant_policies


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0021_tenant_public_media"),
        ("portal", "0003_portal_verification"),
    ]

    operations = [
        migrations.RunPython(apply_tenant_policies, drop_tenant_policies),
    ]
