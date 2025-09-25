# accounts/admin.py
from django.contrib import admin
from .models import User, ClinicRole

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("username", "email", "role", "clinic_code")
    search_fields = ("username", "email")

@admin.register(ClinicRole)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "description")
