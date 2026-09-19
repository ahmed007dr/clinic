"""Extend the isolation policies to the customers' service orders (docs/16).

`portal.ServiceOrder` and `ServiceOrderLine` are tenant-owned; another group
must never read them. Picked up by the derivation in tenants.rls like every
other such model.
"""

from django.db import migrations

from tenants.rls import apply_tenant_policies, drop_tenant_policies


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0026_tenant_listed_in_directory"),
        ("portal", "0004_service_orders"),
    ]

    operations = [
        migrations.RunPython(apply_tenant_policies, drop_tenant_policies),
    ]
