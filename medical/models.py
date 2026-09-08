from django.conf import settings
from django.db import models
from django.utils import timezone

from tenants.models import SerialCounter, TenantOwnedModel


class Visit(TenantOwnedModel):
    """One clinical encounter: what the patient came with, what was found,
    and what was decided.

    An Appointment records that someone was *scheduled*. This records what
    actually happened, which the system had no way to capture before.
    Appointment is optional — walk-ins have none, and a booking that nobody
    attended produces no visit.
    """

    patient = models.ForeignKey(
        "patients.Patient", on_delete=models.PROTECT, related_name="visits"
    )
    appointment = models.ForeignKey(
        "appointments.Appointment", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="visits",
    )
    doctor = models.ForeignKey(
        "employees.Employee", on_delete=models.SET_NULL,
        null=True, blank=True,
        limit_choices_to={"employee_type__name": "Doctor"},
        related_name="visits",
    )
    branch = models.ForeignKey(
        "branches.Branch", on_delete=models.SET_NULL, null=True, blank=True
    )

    visit_date = models.DateTimeField(default=timezone.now, verbose_name="تاريخ الزيارة")
    chief_complaint = models.TextField(blank=True, verbose_name="الشكوى")
    examination = models.TextField(blank=True, verbose_name="الفحص")
    diagnosis = models.TextField(blank=True, verbose_name="التشخيص")
    treatment_plan = models.TextField(blank=True, verbose_name="خطة العلاج")
    follow_up_date = models.DateField(null=True, blank=True, verbose_name="موعد المتابعة")

    serial_number = models.CharField(max_length=20, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["-visit_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "serial_number"], name="uniq_visit_serial_per_tenant"
            )
        ]
        verbose_name = "زيارة"
        verbose_name_plural = "الزيارات"

    def __str__(self):
        return f"{self.serial_number} - {self.patient.name}"

    def save(self, *args, **kwargs):
        if not self.serial_number:
            self.serial_number = SerialCounter.next_serial(
                self.tenant_id, "visit", self.visit_date.date()
            )
        super().save(*args, **kwargs)


class Prescription(TenantOwnedModel):
    """A prescription is a document, not a field on the visit — it is printed,
    handed to the patient and taken to a pharmacy, so it carries its own
    identity and issue date. A visit can produce more than one.

    There is no delete view by design: doc/readme.md §66 requires that medical
    data not change without trace. Edits are recorded by the audit signals.
    """

    visit = models.ForeignKey(
        Visit, on_delete=models.PROTECT, related_name="prescriptions"
    )
    # Denormalised from visit.patient so a patient's prescription history is a
    # single-table query, and so it survives if the visit link ever changes.
    patient = models.ForeignKey(
        "patients.Patient", on_delete=models.PROTECT, related_name="prescriptions"
    )
    doctor = models.ForeignKey(
        "employees.Employee", on_delete=models.SET_NULL,
        null=True, blank=True,
        limit_choices_to={"employee_type__name": "Doctor"},
        related_name="prescriptions",
    )

    issued_at = models.DateTimeField(default=timezone.now, verbose_name="تاريخ الصرف")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")

    serial_number = models.CharField(max_length=20, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["-issued_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "serial_number"],
                name="uniq_prescription_serial_per_tenant",
            )
        ]
        verbose_name = "روشتة"
        verbose_name_plural = "الروشتات"

    def __str__(self):
        return f"{self.serial_number} - {self.patient.name}"

    def save(self, *args, **kwargs):
        if not self.serial_number:
            self.serial_number = SerialCounter.next_serial(
                self.tenant_id, "prescription", self.issued_at.date()
            )
        super().save(*args, **kwargs)


class PrescriptionItem(TenantOwnedModel):
    """One medication line. CASCADE because a line has no meaning apart from
    the prescription that issued it."""

    prescription = models.ForeignKey(
        Prescription, on_delete=models.CASCADE, related_name="items"
    )
    medication = models.CharField(max_length=200, verbose_name="الدواء")
    dosage = models.CharField(max_length=100, blank=True, verbose_name="الجرعة")
    frequency = models.CharField(max_length=100, blank=True, verbose_name="التكرار")
    duration = models.CharField(max_length=100, blank=True, verbose_name="المدة")
    instructions = models.CharField(max_length=300, blank=True, verbose_name="تعليمات")

    class Meta(TenantOwnedModel.Meta):
        ordering = ["id"]
        verbose_name = "دواء"
        verbose_name_plural = "الأدوية"

    def __str__(self):
        return self.medication


def allergy_conflicts(patient, medications):
    """Flag prescribed medications that mention a recorded allergen.

    Deliberately crude substring matching, and deliberately non-blocking:
    doc/readme.md §26 is explicit that the system may surface suggestions but
    never makes the medical decision. This warns; the doctor decides.
    """
    # all_objects deliberately: the patient already pins the tenant, and a
    # safety check must not depend on ambient request context. Reading through
    # the scoped manager would silently return no allergens — and therefore no
    # warnings — from a management command or a background job.
    allergens = [
        substance.strip()
        for substance in Allergy.all_objects.filter(patient=patient).values_list(
            "substance", flat=True
        )
        if substance and substance.strip()
    ]

    conflicts = []
    for medication in medications:
        if not medication:
            continue
        for allergen in allergens:
            if allergen.lower() in medication.lower():
                conflicts.append((medication, allergen))
    return conflicts


class Allergy(TenantOwnedModel):
    """Kept separate from the visit that recorded it: an allergy is a standing
    fact about the patient, and has to be visible on every future encounter,
    not buried in one note."""

    class Severity(models.TextChoices):
        MILD = "mild", "خفيفة"
        MODERATE = "moderate", "متوسطة"
        SEVERE = "severe", "شديدة"

    patient = models.ForeignKey(
        "patients.Patient", on_delete=models.PROTECT, related_name="allergies"
    )
    substance = models.CharField(max_length=200, verbose_name="المادة")
    reaction = models.CharField(max_length=200, blank=True, verbose_name="رد الفعل")
    severity = models.CharField(
        max_length=20, choices=Severity.choices, default=Severity.MODERATE,
        verbose_name="الشدة",
    )
    notes = models.TextField(blank=True, verbose_name="ملاحظات")

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["substance"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "patient", "substance"],
                name="uniq_allergy_per_patient",
            )
        ]
        verbose_name = "حساسية"
        verbose_name_plural = "الحساسية"

    def __str__(self):
        return f"{self.patient.name} - {self.substance}"

    @property
    def is_severe(self):
        return self.severity == self.Severity.SEVERE
