from django.contrib import admin

from .models import Tenant


class TenantOwnedAdmin(admin.ModelAdmin):
    """Admin is operated by platform staff, who work across tenants.

    The default manager is tenant-scoped and fails closed, which would leave
    every changelist empty here, so read through the unfiltered manager.
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
