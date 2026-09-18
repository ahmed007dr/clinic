"""Receipts, the shift report and the payments export — the server-rendered pages
React links to. (Recording and listing money is /api/payments/, /api/expenses/
and /api/shifts/.)"""

from django.urls import path

from .views import commission_report_print, expense_print, payment_list_export, payment_print, shift_print

app_name = "billing"

urlpatterns = [
    path('<uuid:uuid>/print/', payment_print, name='payment_print'),
    path('export/', payment_list_export, name='payment_list_export'),
    path('expense/<uuid:uuid>/print/', expense_print, name='expense_print'),
    path('shift/<uuid:uuid>/print/', shift_print, name='shift_print'),
    path('commissions/print/', commission_report_print, name='commission_report_print'),
]
