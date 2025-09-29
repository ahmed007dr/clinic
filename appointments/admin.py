from django.contrib import admin
from .models import Appointment

@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ("patient", "doctor", "service", "scheduled_date", "status", "price", "branch", "created_at")
    list_filter = ("status", "scheduled_date", "branch")  # يعمل مع status كـ CharField
    search_fields = ("patient__name", "doctor__name", "service__name")
    date_hierarchy = "scheduled_date"
    ordering = ("-scheduled_date",)
    fieldsets = (
        (None, {"fields": ("patient", "doctor", "service", "scheduled_date")}),
        ("Details", {"fields": ("status", "price", "branch", "notes")}),
        ("Audit", {"fields": ("created_by", "created_at")}),
    )