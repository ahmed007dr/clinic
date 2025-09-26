# employees/admin.py
from django.contrib import admin
from .models import Employee, Specialization, EmployeeType

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("name", "employee_type", "hire_date", "branch", "salary_value")
    search_fields = ("name", "national_id", "phone1", "email")
    list_filter = ("employee_type", "branch", "hire_date")
    filter_horizontal = ("specializations",)
    ordering = ("name",)
    fieldsets = (
        (None, {"fields": ("name", "employee_type", "specializations", "national_id")}),
        ("Contact Info", {"fields": ("phone1", "phone2", "email", "branch")}),
        ("Employment", {"fields": ("hire_date", "salary_type", "salary_value")}),
    )

@admin.register(Specialization)
class SpecializationAdmin(admin.ModelAdmin):
    list_display = ("name", "description")
    search_fields = ("name",)
    ordering = ("name",)

@admin.register(EmployeeType)
class EmployeeTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "description")
    search_fields = ("name",)
    ordering = ("name",)
