from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("user", "action", "model_name", "object_id", "created_at")
    list_filter = ("action", "created_at")
    search_fields = ("user__username", "model_name", "description")
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False  # مفيش إضافة يدوي

    def has_change_permission(self, request, obj=None):
        return False  # مفيش تعديل يدوي
