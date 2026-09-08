from django.contrib import admin

from tenants.admin import TenantOwnedAdmin

from .models import Allergy, Visit


@admin.register(Visit)
class VisitAdmin(TenantOwnedAdmin):
    list_display = ("serial_number", "patient", "doctor", "visit_date", "branch")
    list_filter = ("branch", "visit_date")
    search_fields = ("serial_number", "patient__name", "diagnosis")
    date_hierarchy = "visit_date"
    readonly_fields = ("uuid", "serial_number", "created_at", "updated_at")


@admin.register(Allergy)
class AllergyAdmin(TenantOwnedAdmin):
    list_display = ("patient", "substance", "severity", "recorded_at")
    list_filter = ("severity",)
    search_fields = ("patient__name", "substance")
    readonly_fields = ("uuid", "recorded_at")
