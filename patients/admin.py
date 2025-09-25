# patients/admin.py
from django.contrib import admin
from .models import Patient

@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("name", "phone1", "gender", "birth_date")
    search_fields = ("name", "phone1", "national_id")
