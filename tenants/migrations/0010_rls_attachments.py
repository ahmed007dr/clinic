"""Extend the isolation policies to medical.MedicalAttachment.

The protected set is derived from the models (tenants/rls.py). Note what this
does and does not cover: the policy protects the *rows*, so metadata about a
document cannot be read across tenants. The file bytes are protected separately,
by being stored outside MEDIA_ROOT and served only through a view — see
medical/attachments.py. Neither substitutes for the other.
"""

from django.db import migrations

from tenants.rls import apply_tenant_policies, drop_tenant_policies


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0009_rls_lab_results"),
        ("medical", "0007_medicalattachment"),
    ]

    operations = [
        migrations.RunPython(apply_tenant_policies, drop_tenant_policies),
    ]
