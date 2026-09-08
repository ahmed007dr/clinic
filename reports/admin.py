from django.contrib import admin
from tenants.admin import TenantOwnedAdmin
from .models import ReportRecipient

@admin.register(ReportRecipient)
class ReportRecipientAdmin(TenantOwnedAdmin):
    list_display = ('email', 'name', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('email', 'name')