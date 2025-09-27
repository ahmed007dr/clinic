from django.contrib import admin
from .models import ReportRecipient

@admin.register(ReportRecipient)
class ReportRecipientAdmin(admin.ModelAdmin):
    list_display = ('email', 'name', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('email', 'name')