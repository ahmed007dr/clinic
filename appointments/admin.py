from django.contrib import admin
from tenants.admin import TenantOwnedAdmin
from .models import Appointment

@admin.register(Appointment)
class AppointmentAdmin(TenantOwnedAdmin):
    list_display = ("patient", "doctor", "service", "scheduled_date", "status", "price", "branch", "created_at")
    list_filter = ("status", "scheduled_date", "branch")  # يعمل مع status كـ CharField
    search_fields = ("patient__name", "doctor__name", "service__name")
    date_hierarchy = "scheduled_date"
    ordering = ("-scheduled_date",)
    # created_at is auto_now_add, so editable=False. Naming a non-editable field
    # in fieldsets without also marking it readonly raises FieldError when the
    # form is built — the add/change pages returned 500, not a validation error.
    # Readonly keeps it displayed, which is what the "Audit" section is for.
    readonly_fields = ("created_at",)
    fieldsets = (
        (None, {"fields": ("patient", "doctor", "service", "scheduled_date")}),
        ("Details", {"fields": ("status", "price", "branch", "notes")}),
        ("Audit", {"fields": ("created_by", "created_at")}),
    )