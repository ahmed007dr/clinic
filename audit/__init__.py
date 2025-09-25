# audit/admin.py
from django.contrib import admin
from .models import AuditLog

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("user", "action", "model_name", "object_id", "created_at")
    list_filter = ("action", "model_name", "created_at")
    search_fields = ("user__username", "model_name", "object_id")
