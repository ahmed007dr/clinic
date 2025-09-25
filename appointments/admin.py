# appointments/admin.py
from django.contrib import admin
from .models import Appointment

@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ("patient", "doctor", "service", "scheduled_date", "status", "price")
    list_filter = ("status", "scheduled_date")
    search_fields = ("patient__name", "doctor__name")
