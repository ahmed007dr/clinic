from django.contrib import admin

from tenants.admin import TenantOwnedAdmin

from .models import (
    Allergy,
    LabResult,
    MedicalAttachment,
    Prescription,
    PrescriptionItem,
    Procedure,
    TreatmentPlan,
    TreatmentSession,
    Visit,
)


@admin.register(Visit)
class VisitAdmin(TenantOwnedAdmin):
    list_display = ("serial_number", "patient", "doctor", "visit_date", "branch")
    list_filter = ("branch", "visit_date")
    search_fields = ("serial_number", "patient__name", "diagnosis")
    date_hierarchy = "visit_date"
    readonly_fields = ("uuid", "serial_number", "created_at", "updated_at")


@admin.register(Allergy)
class AllergyAdmin(TenantOwnedAdmin):
    list_display = ("patient", "substance", "severity", "recorded_at")
    list_filter = ("severity",)
    search_fields = ("patient__name", "substance")
    readonly_fields = ("uuid", "recorded_at")


@admin.register(TreatmentPlan)
class TreatmentPlanAdmin(TenantOwnedAdmin):
    list_display = ("serial_number", "title", "patient", "doctor", "status", "start_date")
    list_filter = ("status", "branch")
    search_fields = ("serial_number", "title", "patient__name")
    date_hierarchy = "start_date"
    readonly_fields = ("uuid", "serial_number", "created_at", "updated_at")


@admin.register(TreatmentSession)
class TreatmentSessionAdmin(TenantOwnedAdmin):
    list_display = ("plan", "sequence", "patient", "scheduled_date", "status", "total_amount")
    list_filter = ("status", "branch")
    search_fields = ("plan__serial_number", "patient__name")
    date_hierarchy = "scheduled_date"
    readonly_fields = ("uuid", "created_at", "updated_at")


@admin.register(MedicalAttachment)
class MedicalAttachmentAdmin(TenantOwnedAdmin):
    list_display = ("serial_number", "title", "patient", "category", "size_bytes", "created_at")
    list_filter = ("category", "branch")
    search_fields = ("serial_number", "title", "patient__name", "original_filename")
    date_hierarchy = "created_at"
    readonly_fields = (
        "uuid", "serial_number", "content_type", "size_bytes", "checksum",
        "original_filename", "created_at", "updated_at",
    )


@admin.register(LabResult)
class LabResultAdmin(TenantOwnedAdmin):
    list_display = ("serial_number", "test_name", "patient", "flag", "status", "ordered_at")
    list_filter = ("flag", "status", "branch")
    search_fields = ("serial_number", "test_name", "patient__name", "lab_name")
    date_hierarchy = "ordered_at"
    readonly_fields = ("uuid", "serial_number", "created_at", "updated_at")


@admin.register(Procedure)
class ProcedureAdmin(TenantOwnedAdmin):
    list_display = ("serial_number", "name", "patient", "doctor", "status", "performed_at")
    list_filter = ("status", "branch")
    search_fields = ("serial_number", "name", "patient__name", "body_site")
    date_hierarchy = "performed_at"
    readonly_fields = ("uuid", "serial_number", "created_at", "updated_at")


class PrescriptionItemInline(admin.TabularInline):
    model = PrescriptionItem
    extra = 0


@admin.register(Prescription)
class PrescriptionAdmin(TenantOwnedAdmin):
    list_display = ("serial_number", "patient", "doctor", "issued_at")
    search_fields = ("serial_number", "patient__name")
    date_hierarchy = "issued_at"
    inlines = [PrescriptionItemInline]
    readonly_fields = ("uuid", "serial_number", "created_at")
