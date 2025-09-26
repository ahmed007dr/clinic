# billing/admin.py
from django.contrib import admin
from .models import Payment, PaymentMethod, Expense, ExpenseCategory

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
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
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ("name", "description")
    search_fields = ("name",)
    ordering = ("name",)

@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("category", "amount", "date", "branch", "employee", "doctor")
    search_fields = ("category__name", "employee__name", "doctor__name")
    list_filter = ("category", "date", "branch")
    date_hierarchy = "date"
    ordering = ("-date",)
    fieldsets = (
        (None, {"fields": ("category", "branch", "amount")}),
        ("Related", {"fields": ("employee", "doctor")}),
        ("Details", {"fields": ("date", "notes", "created_by")}),
    )

@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "description")
    search_fields = ("name",)
    ordering = ("name",)
