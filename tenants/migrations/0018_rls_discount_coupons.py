"""Extend the isolation policies to discount coupons.

`billing.DiscountCoupon` is tenant-owned: it names a patient and an amount, so
another clinic must never read it. Picked up by the derivation in tenants.rls
like every other such model.
"""

from django.db import migrations

from tenants.rls import apply_tenant_policies, drop_tenant_policies


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0017_rls_doctor_contracts"),
        ("billing", "0010_discountcoupon"),
    ]

    operations = [
        migrations.RunPython(apply_tenant_policies, drop_tenant_policies),
    ]
