"""Introduce the group Owner, without changing anyone's access.

Until now "Admin" meant "sees every clinic in the group". From here on it
means one clinic, and the group-wide role is "Owner" (accounts/roles.py).

So every existing Admin becomes an Owner: each keeps exactly the reach they had
this morning, and nobody gains or loses access by deploying this. Assigning
clinic Admins is then a deliberate act by the Owner, not a side effect of a
migration.

`ClinicRole` is tenant-owned, so the tenant is bound around each group's
changes — the same pattern as subscriptions.0002 — and this works whether or
not the row-level security policies are installed.
"""

from django.db import migrations


def bind_tenant(schema_editor, tenant_id):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('app.current_tenant_id', %s, false)",
            [str(tenant_id) if tenant_id is not None else ""],
        )


def promote_admins_to_owner(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    ClinicRole = apps.get_model("accounts", "ClinicRole")
    User = apps.get_model("accounts", "User")

    for tenant in Tenant.objects.all():
        bind_tenant(schema_editor, tenant.id)
        try:
            owner, _ = ClinicRole.objects.get_or_create(
                tenant=tenant, name="Owner",
                defaults={"description": "Medical group owner"},
            )
            admin = ClinicRole.objects.filter(tenant=tenant, name="Admin").first()
            if admin is not None:
                User.objects.filter(tenant=tenant, role=admin).update(role=owner)
        finally:
            bind_tenant(schema_editor, None)


def demote_owners_to_admin(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    ClinicRole = apps.get_model("accounts", "ClinicRole")
    User = apps.get_model("accounts", "User")

    for tenant in Tenant.objects.all():
        bind_tenant(schema_editor, tenant.id)
        try:
            owner = ClinicRole.objects.filter(tenant=tenant, name="Owner").first()
            if owner is None:
                continue
            admin, _ = ClinicRole.objects.get_or_create(tenant=tenant, name="Admin")
            User.objects.filter(tenant=tenant, role=owner).update(role=admin)
            owner.delete()
        finally:
            bind_tenant(schema_editor, None)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_add_uuid"),
        ("tenants", "0013_rls_portal"),
    ]

    operations = [
        migrations.RunPython(promote_admins_to_owner, demote_owners_to_admin),
    ]
