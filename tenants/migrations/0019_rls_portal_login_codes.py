"""Extend the isolation policies to portal login codes.

`portal.PortalLoginCode` is tenant-owned and holds a live sign-in credential
(hashed); another clinic must never read it. Picked up by the derivation in
tenants.rls like every other such model.
"""

from django.db import migrations

from tenants.rls import apply_tenant_policies, drop_tenant_policies


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0018_rls_discount_coupons"),
        ("portal", "0002_login_codes"),
    ]

    operations = [
        migrations.RunPython(apply_tenant_policies, drop_tenant_policies),
    ]
