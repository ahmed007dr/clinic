# employees/admin.py
from django.contrib import admin
from .models import Employee, Specialization

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("name", "employee_type", "hire_date")
    search_fields = ("name", "employee_type")

@admin.register(Specialization)
class SpecializationAdmin(admin.ModelAdmin):
    list_display = ("name",)
