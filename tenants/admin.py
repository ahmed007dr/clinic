from django.contrib import admin

from .models import Tenant


class TenantOwnedAdmin(admin.ModelAdmin):
    """Admin is operated by platform staff, who work across tenants.

    The default manager is tenant-scoped and fails closed, which would leave
    every changelist empty here, so read through the unfiltered manager.

    Known limitation under PostgreSQL row-level security (tenants.0005):
    `all_objects` bypasses the manager but not the policies, and platform staff
    carry no tenant, so these changelists come back empty rather than
    cross-tenant. That fails closed — it is a loss of function, not a leak —
    and it is why cross-tenant platform administration is scheduled with the
    platform-admin work in P4, where it can be built on a deliberate second
    connection using a BYPASSRLS role. Widening the policies to accommodate the
    admin would give that reach to every query in the application.
    """

    def get_queryset(self, request):
        queryset = self.model.all_objects.get_queryset()
        ordering = self.get_ordering(request)
        if ordering:
            queryset = queryset.order_by(*ordering)
        return queryset


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("name", "slug")
    readonly_fields = ("uuid", "created_at")

    def save_model(self, request, obj, form, change):
        """Seed a tenant created here, so it isn't born unusable.

        Without this, an admin-created tenant has no roles and no Doctor type
        until the next migrate happens to run the backstop. It still has no
        branch or user — `manage.py create_tenant` is the complete path.
        """
        super().save_model(request, obj, form, change)
        if not change:
            from .provisioning import provision_tenant_defaults

            provision_tenant_defaults(obj)
