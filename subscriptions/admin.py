from django.contrib import admin

from .models import Plan, Subscription


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    """Registered normally, not through TenantOwnedAdmin.

    The catalogue is platform-level: it has no tenant column, carries no
    row-level security policy, and is exactly the kind of thing platform staff
    should administer. Managing tiers is the SaaS admin's job per §10.
    """

    list_display = ("code", "name", "billing_period", "price", "is_active", "is_public")
    list_filter = ("billing_period", "is_active", "is_public")
    search_fields = ("code", "name")
    readonly_fields = ("created_at", "updated_at")


# Subscription is deliberately NOT registered. It is tenant-owned and therefore
# RLS-protected, so a changelist here would come back empty for platform staff —
# the same misleading blank page that ADMIN-002 removed for every other
# tenant-owned model. Managing a clinic's subscription belongs with the "act as
# tenant" work, where the tenant is chosen explicitly and the action is audited.
