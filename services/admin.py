# services/admin.py
from django.contrib import admin
from .models import Service

@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("name", "specialization", "base_price")
    search_fields = ("name",)
