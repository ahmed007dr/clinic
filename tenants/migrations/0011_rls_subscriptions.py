"""Extend the isolation policies to subscriptions.Subscription.

Derived from the models as always. Note what is *not* covered: `Plan` has no
tenant foreign key, because the catalogue is platform-level and shared, so the
derivation skips it — which is correct. A plan is not anybody's private data;
a subscription is.
"""

from django.db import migrations

from tenants.rls import apply_tenant_policies, drop_tenant_policies


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0010_rls_attachments"),
        ("subscriptions", "0002_seed_plans_and_grandfather_tenants"),
    ]

    operations = [
        migrations.RunPython(apply_tenant_policies, drop_tenant_policies),
    ]
