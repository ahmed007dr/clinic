# patients/admin.py
from django.contrib import admin
from .models import Patient

@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("name", "phone1", "gender", "birth_date", "national_id")
    search_fields = ("name", "phone1", "phone2", "national_id", "email")
    list_filter = ("gender", "birth_date")
    ordering = ("name",)
    fieldsets = (
        (None, {"fields": ("name", "national_id", "gender", "birth_date")}),
        ("Contact Info", {"fields": ("phone1", "phone2", "email", "address")}),
        ("Additional Info", {"fields": ("marital_status", "photo", "notes")}),
    )
