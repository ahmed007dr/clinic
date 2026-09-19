"""Extend the isolation policies to the email log.

`notifications.EmailLog` is tenant-owned and holds the text of messages sent to
a clinic's patients and staff; another clinic must never read it. Picked up by
the derivation in tenants.rls like every other such model.
"""

from django.db import migrations

from tenants.rls import apply_tenant_policies, drop_tenant_policies


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0019_rls_portal_login_codes"),
        ("notifications", "0006_email_log"),
    ]

    operations = [
        migrations.RunPython(apply_tenant_policies, drop_tenant_policies),
    ]
