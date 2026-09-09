from django.contrib import admin

from .models import Tenant


class TenantOwnedAdmin(admin.ModelAdmin):
    """Disabled: tenant-owned models are not administrable from Django admin.

    This class used to read through `all_objects` so platform staff could work
    across tenants. An audit of what it actually did found that unusable, in two
    independent ways:

    * Under the row-level security policies (tenants.0005), `all_objects`
      bypasses the application-layer manager but not the database. Platform
      staff carry no tenant, so every changelist returned zero rows against a
      database holding real data — 258 notifications, 80 appointments, 55
      patients, and so on.
    * Every foreign-key dropdown and list_filter was *already* empty before RLS
      existed, and had been since TENANT-006. Admin builds those from the
      related model's `_default_manager`, which is the tenant-scoped one, and
      this class only ever overrode `get_queryset`. So creating and editing
      were impossible regardless of the database layer.

    Empty changelists are worse than absent ones: they read as "this clinic has
    no patients" rather than "you cannot see this here". So access is denied
    outright, in one place, rather than left silently misleading.

    What is deliberately *not* done to fix this, and why: no BYPASSRLS role and
    no privileged connection (a standing bypass is a permanent risk, and the
    only genuine need is read-only inspection), and no bypass flag in the
    policies (privilege must come from the database role you authenticate as,
    which application code cannot change — not from a GUC anything could set).

    The replacement is per-tenant, read-only and audited: platform staff select
    one tenant and the application enters `tenant_context` for it on the normal
    connection, so RLS permits exactly that tenant's rows and the isolation
    model is unchanged. Until that exists, these models are reachable only
    through the tenant-facing application.

    `Tenant`, `User`, `AuditLog` and `Group` carry no tenant-isolation policy
    and are administered normally — they do not use this class.
    """

    # Denied at the module level too, so the models vanish from the admin index
    # instead of appearing and then 403-ing when clicked.
    def has_module_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


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
