# billing/admin.py
from django.contrib import admin
from tenants.admin import TenantOwnedAdmin
from .models import Payment, PaymentMethod, Expense, ExpenseCategory

@admin.register(Payment)
class PaymentAdmin(TenantOwnedAdmin):
    list_display = ("receipt_number", "patient", "amount", "method", "date", "branch")
    search_fields = ("receipt_number", "patient__name")
    list_filter = ("method", "date", "branch")
    date_hierarchy = "date"
    ordering = ("-date",)
    fieldsets = (
        (None, {"fields": ("appointment", "patient", "method", "receipt_number")}),
        ("Details", {"fields": ("amount", "branch", "notes")}),
    )

@admin.register(PaymentMethod)
class PaymentMethodAdmin(TenantOwnedAdmin):
    list_display = ("name", "description")
    search_fields = ("name",)
    ordering = ("name",)

@admin.register(Expense)
class ExpenseAdmin(TenantOwnedAdmin):
    list_display = ("category", "amount", "date", "branch", "employee")
    search_fields = ("category__name", "employee__name")
    list_filter = ("category", "date", "branch")
    date_hierarchy = "date"
    ordering = ("-date",)
    fieldsets = (
        (None, {"fields": ("category", "branch", "amount")}),
        ("Related", {"fields": ("employee",)}), 
        ("Details", {"fields": ("date", "notes", "created_by")}),
    )

@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(TenantOwnedAdmin):
    list_display = ("name", "description")
    search_fields = ("name",)
    ordering = ("name",)