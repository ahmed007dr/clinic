# billing/admin.py
from django.contrib import admin
from .models import Payment, PaymentMethod

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("receipt_number", "patient", "amount", "method", "date")
    search_fields = ("receipt_number", "patient__name")

@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ("name", "description")
