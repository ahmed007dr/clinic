"""Seed the catalogue, and give every existing tenant a subscription.

The second half is not optional. Entitlements fail closed: `get_limit` returns
0 for a tenant with no active subscription, because treating "unknown" as
"unrestricted" is how a lapsed customer grows without bound. That is the right
default for a new tenant and a disaster for an existing one — every clinic
already running would be unable to add a branch or register a patient the
moment the enforcement lands.

So existing tenants are grandfathered onto Enterprise: unlimited, everything
on. That is deliberately generous. The alternative is guessing what each
clinic bought and getting it wrong in the direction that breaks their day, and
a commercial decision to downgrade someone can be taken later by a person who
knows the contract. The subscriptions carry a note saying exactly that.

The tenant GUC is bound around each insert so this works whether or not the
row-level security policies are already in place — the ordering happens to be
safe today, and relying on that would be a trap for whoever reorders next.
"""

from django.db import migrations

PLANS = [
    {
        "code": "basic",
        "name": "Basic",
        "description": "عيادة واحدة، فريق صغير.",
        "price": 500,
        "max_branches": 1,
        "max_doctors": 2,
        "max_staff": 5,
        "max_patients": 500,
        "max_storage_mb": 1024,
        "features": {
            "whatsapp": False, "online_payments": False, "advanced_analytics": False,
            "ai": False, "packages": False, "reports": True,
        },
    },
    {
        "code": "professional",
        "name": "Professional",
        "description": "عدة فروع، مع الحزم والمدفوعات الإلكترونية.",
        "price": 1500,
        "max_branches": 3,
        "max_doctors": 10,
        "max_staff": 25,
        "max_patients": 5000,
        "max_storage_mb": 10240,
        "features": {
            "whatsapp": True, "online_payments": True, "advanced_analytics": False,
            "ai": False, "packages": True, "reports": True,
        },
    },
    {
        "code": "enterprise",
        "name": "Enterprise",
        "description": "بدون حدود، مع كل الخصائص.",
        "price": 4000,
        "max_branches": None,
        "max_doctors": None,
        "max_staff": None,
        "max_patients": None,
        "max_storage_mb": None,
        "features": {
            "whatsapp": True, "online_payments": True, "advanced_analytics": True,
            "ai": True, "packages": True, "reports": True,
        },
    },
]

GRANDFATHER_NOTE = (
    "Grandfathered by subscriptions.0002. Entitlements fail closed, so an "
    "existing tenant without a subscription would have been blocked from "
    "adding branches or patients. Enterprise was chosen because guessing a "
    "smaller tier would break a running clinic; downgrade deliberately once "
    "the contract is known."
)


def bind_tenant(schema_editor, tenant_id):
    """Declare which tenant the connection is acting for, so the insert passes
    the RLS WITH CHECK if the policies are already installed."""
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('app.current_tenant_id', %s, false)",
            [str(tenant_id) if tenant_id is not None else ""],
        )


def seed(apps, schema_editor):
    Plan = apps.get_model("subscriptions", "Plan")
    Subscription = apps.get_model("subscriptions", "Subscription")
    Tenant = apps.get_model("tenants", "Tenant")

    for spec in PLANS:
        Plan.objects.update_or_create(code=spec["code"], defaults=spec)

    enterprise = Plan.objects.get(code="enterprise")
    for tenant in Tenant.objects.all():
        bind_tenant(schema_editor, tenant.id)
        try:
            if Subscription.objects.filter(tenant=tenant, status="active").exists():
                continue
            Subscription.objects.create(
                tenant=tenant, plan=enterprise, status="active",
                notes=GRANDFATHER_NOTE,
            )
        finally:
            bind_tenant(schema_editor, None)


def unseed(apps, schema_editor):
    Plan = apps.get_model("subscriptions", "Plan")
    Subscription = apps.get_model("subscriptions", "Subscription")
    Tenant = apps.get_model("tenants", "Tenant")

    for tenant in Tenant.objects.all():
        bind_tenant(schema_editor, tenant.id)
        try:
            Subscription.objects.filter(tenant=tenant, notes=GRANDFATHER_NOTE).delete()
        finally:
            bind_tenant(schema_editor, None)
    Plan.objects.filter(code__in=[spec["code"] for spec in PLANS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("subscriptions", "0001_initial"),
        ("tenants", "0010_rls_attachments"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
