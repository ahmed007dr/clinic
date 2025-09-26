from django.contrib import admin
from .models import Branch

@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "phone", "email")
    search_fields = ("name", "code", "phone", "email")
    ordering = ("name",)
    fieldsets = (
        (None, {"fields": ("name", "code")}),
        ("Contact Info", {"fields": ("address", "phone", "email")}),
    )
