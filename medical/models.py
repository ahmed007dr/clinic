from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from tenants.models import SerialCounter, TenantOwnedModel


def today():
    """The project runs with USE_TZ = False, so `timezone.now()` is naive and
    `timezone.localdate()` refuses it. Kept as a named module-level function
    because a field default has to stay importable for migrations."""
    return timezone.now().date()


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


class TreatmentPlan(TenantOwnedModel):
    """A course of treatment delivered over several visits — doc/readme.md §28.

    Distinct from `Visit.treatment_plan`, which is a free-text note about one
    encounter and stays as it is. This is the structured version: a named
    course ("Laser Treatment, 6 sessions") that outlives any single visit and
    that sessions are booked against.

    `planned_sessions` is the intent, not the truth. What was actually
    delivered is counted from the sessions themselves, because courses get
    extended, cut short, or abandoned, and a stored counter would drift.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "مسودة"
        ACTIVE = "active", "جارية"
        COMPLETED = "completed", "مكتملة"
        CANCELLED = "cancelled", "ملغاة"

    patient = models.ForeignKey(
        "patients.Patient", on_delete=models.PROTECT, related_name="treatment_plans"
    )
    # The consultation that led to the plan. Optional and SET_NULL: a course
    # can be agreed outside a recorded visit, and losing the link must not take
    # the plan with it.
    visit = models.ForeignKey(
        Visit, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="treatment_plans",
    )
    doctor = models.ForeignKey(
        "employees.Employee", on_delete=models.SET_NULL,
        null=True, blank=True,
        limit_choices_to={"employee_type__name": "Doctor"},
        related_name="treatment_plans",
    )
    branch = models.ForeignKey(
        "branches.Branch", on_delete=models.SET_NULL, null=True, blank=True
    )
    # What the course delivers, for pricing. Optional because a plan can be
    # written before the service catalogue has an entry for it.
    service = models.ForeignKey(
        "services.Service", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="treatment_plans",
    )

    title = models.CharField(max_length=200, verbose_name="اسم الخطة")
    planned_sessions = models.PositiveIntegerField(
        default=1, validators=[MinValueValidator(1)], verbose_name="عدد الجلسات المخططة"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE,
        verbose_name="الحالة",
    )
    start_date = models.DateField(default=today, verbose_name="تاريخ البدء")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")

    serial_number = models.CharField(max_length=20, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["-start_date", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "serial_number"],
                name="uniq_treatment_plan_serial_per_tenant",
            )
        ]
        verbose_name = "خطة علاج"
        verbose_name_plural = "خطط العلاج"

    def __str__(self):
        return f"{self.serial_number} - {self.title}"

    def save(self, *args, **kwargs):
        if not self.serial_number:
            self.serial_number = SerialCounter.next_serial(
                self.tenant_id, "treatment_plan", self.start_date
            )
        super().save(*args, **kwargs)

    @property
    def is_open(self):
        return self.status in {self.Status.DRAFT, self.Status.ACTIVE}

    @property
    def completed_sessions(self):
        """Counted, never stored. A cached total drifts the moment a session is
        cancelled or added, and the sessions are the record of what happened.

        `self.sessions` is the tenant-scoped reverse accessor, so outside a
        request — a management command, a scheduled report — this returns 0
        rather than raising. Callers running outside a request must enter
        `tenant_context` first; the views and templates are inside one.
        """
        return self.sessions.filter(status=TreatmentSession.Status.COMPLETED).count()

    @property
    def remaining_sessions(self):
        return max(self.planned_sessions - self.completed_sessions, 0)


class TreatmentSession(TenantOwnedModel):
    """One delivered session of a treatment plan — doc/readme.md §28.

    Carries its own money rather than deferring to the plan, because §29's
    quantity-priced services (laser pulses, where 25 pulses is 25 x the unit
    price) are decided per session: the doctor sees the skin on the day.

    `unit_price` is seeded from the service when the session is created and
    then stands on its own. Packages and promotions (§40, §41) will change how
    the *initial* figure is worked out, not where it is kept — so a later
    pricing engine fills this field instead of replacing it.
    """

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "مجدولة"
        COMPLETED = "completed", "مكتملة"
        CANCELLED = "cancelled", "ملغاة"
        NO_SHOW = "no_show", "لم يحضر"

    plan = models.ForeignKey(
        TreatmentPlan, on_delete=models.PROTECT, related_name="sessions"
    )
    # Denormalised from plan.patient, for the same reason Prescription does it:
    # a patient's session history stays a single-table query.
    patient = models.ForeignKey(
        "patients.Patient", on_delete=models.PROTECT, related_name="treatment_sessions"
    )
    doctor = models.ForeignKey(
        "employees.Employee", on_delete=models.SET_NULL,
        null=True, blank=True,
        limit_choices_to={"employee_type__name": "Doctor"},
        related_name="treatment_sessions",
    )
    branch = models.ForeignKey(
        "branches.Branch", on_delete=models.SET_NULL, null=True, blank=True
    )
    service = models.ForeignKey(
        "services.Service", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="treatment_sessions",
    )
    # The receipt covering this session. SET_NULL, not PROTECT: billing owns
    # its own retention rules, and a session must not become undeletable
    # because of how it was paid for.
    payment = models.ForeignKey(
        "billing.Payment", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="treatment_sessions",
    )

    sequence = models.PositiveIntegerField(verbose_name="رقم الجلسة")
    scheduled_date = models.DateTimeField(default=timezone.now, verbose_name="موعد الجلسة")
    performed_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ التنفيذ")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.SCHEDULED,
        verbose_name="الحالة",
    )

    quantity = models.PositiveIntegerField(
        default=1, validators=[MinValueValidator(1)], verbose_name="الكمية"
    )
    unit_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        validators=[MinValueValidator(0)], verbose_name="سعر الوحدة",
    )
    discount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        validators=[MinValueValidator(0)], verbose_name="الخصم",
    )

    result = models.TextField(blank=True, verbose_name="النتيجة")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["plan_id", "sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "plan", "sequence"],
                name="uniq_session_sequence_per_plan",
            ),
            # Enforced by the database, not only the form: a discount larger
            # than the line it discounts turns revenue negative, and every
            # total downstream with it. BE-005 put a floor under the individual
            # amounts; this is the relationship between them.
            models.CheckConstraint(
                check=models.Q(discount__lte=models.F("unit_price") * models.F("quantity")),
                name="session_discount_within_total",
            ),
        ]
        verbose_name = "جلسة علاج"
        verbose_name_plural = "جلسات العلاج"

    def __str__(self):
        return f"{self.plan.serial_number} - جلسة {self.sequence}"

    @property
    def gross_amount(self):
        return self.unit_price * self.quantity

    @property
    def total_amount(self):
        return self.gross_amount - self.discount

    def save(self, *args, **kwargs):
        if not self.sequence:
            self.sequence = self._next_sequence()
        super().save(*args, **kwargs)

    def _next_sequence(self):
        """Next free number within this plan.

        Not SerialCounter: that issues per-tenant-per-day identifiers, and this
        is a position in a course — session 3 of 6. Two sessions added for the
        same plan at the same instant can still collide, and the unique
        constraint above turns that into an error rather than a duplicate
        number. Acceptable: sessions are added one at a time by a clinician.
        """
        last = (
            TreatmentSession.all_objects.filter(tenant_id=self.tenant_id, plan=self.plan)
            .order_by("-sequence")
            .values_list("sequence", flat=True)
            .first()
        )
        return (last or 0) + 1


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
