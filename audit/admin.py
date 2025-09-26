from django.contrib import admin
from .models import AuditLog

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("user", "action", "model_name", "object_id", "created_at", "ip_address")
    list_filter = ("action", "created_at", "model_name")
    search_fields = ("user__username", "model_name", "description")
    readonly_fields = [f.name for f in AuditLog._meta.fields]
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return False
    def has_delete_permission(self, request, obj=None):
        return False
