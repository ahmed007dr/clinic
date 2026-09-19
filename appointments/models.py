from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils import timezone
from tenants.models import SerialCounter, TenantOwnedModel

class Appointment(TenantOwnedModel):
    STATUS_CHOICES = [
        ("entered", "تم الدخول"),
        ("waiting", "الانتظار"),
        ("called", "تم الاتصال بالهاتف"),
        ("quick", "حجز سريع"),
        # From the patient portal; reception confirms it (docs/12, D3).
        ("requested", "طلب من المريض"),
        # Outcomes, so the group dashboard can count what actually happened.
        ("completed", "مكتمل"),
        ("cancelled", "ملغي"),
        ("no_show", "لم يحضر"),
    ]

    class Source(models.TextChoices):
        """Where the booking came from, so a manager can tell a website booking
        from one made at the desk (docs/15). Reception is the default: every
        booking that existed before this field was made by staff."""

        PUBLIC_PORTAL = "portal", "الموقع (بوابة المرضى)"
        RECEPTION = "reception", "الاستقبال"
        ADMIN = "admin", "الإدارة"
        PHONE = "phone", "الهاتف"
        WHATSAPP = "whatsapp", "واتساب"

    patient = models.ForeignKey('patients.Patient', on_delete=models.CASCADE)
    doctor = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={"employee_type__name": "Doctor"}
    )
    specialization = models.ForeignKey('employees.Specialization', on_delete=models.SET_NULL, null=True, blank=True)
    service = models.ForeignKey('services.Service', on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="waiting")
    branch = models.ForeignKey('branches.Branch', on_delete=models.SET_NULL, null=True, blank=True)
    scheduled_date = models.DateTimeField()
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    # For a service sold by quantity (services.Service.requires_quantity): how
    # many, and the price of one when it was booked. `price` is then the total,
    # unit price × quantity. Both empty for a service priced as one thing.
    quantity = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)]
    )
    unit_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)]
    )
    # True while the quantity is only an estimate: the service lets the doctor set
    # it (`Service.doctor_sets_quantity`) and the doctor has not yet. The total
    # can still change, so the desk knows what is left to collect is not final.
    quantity_is_estimate = models.BooleanField(default=False)
    # A coupon applied at booking (billing.DiscountCoupon): the booking keeps
    # the original price, the discount and the coupon, and what the patient
    # owes before going in is the net (`net_price`).
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    coupon = models.ForeignKey(
        'billing.DiscountCoupon', on_delete=models.SET_NULL, null=True, blank=True, related_name='appointments'
    )
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.RECEPTION)
    # A patient's request to move this booking (docs/15, Phase 6): the time they
    # would like and a note. Nothing moves until the clinic agrees it and edits
    # `scheduled_date`, which clears the request.
    reschedule_requested_for = models.DateTimeField(null=True, blank=True)
    reschedule_note = models.CharField(max_length=300, blank=True, default="")
    created_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)
    serial_number = models.CharField(max_length=20, blank=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "serial_number"], name="uniq_appointment_serial_per_tenant")
        ]
        indexes = [
            models.Index(fields=["tenant", "scheduled_date"], name="appointment_date_idx"),
            models.Index(fields=["tenant", "branch", "status"], name="appointment_branch_status_idx"),
        ]

    @property
    def net_price(self):
        """What the patient owes for this booking: price less discount."""
        return max((self.price or 0) - (self.discount or 0), 0)

    def save(self, *args, **kwargs):
        if not self.serial_number:
            self.serial_number = SerialCounter.next_serial(
                self.tenant_id, "appointment", self.scheduled_date.date()
            )
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.serial_number} - {self.patient.name}"


class DoctorSchedule(TenantOwnedModel):
    """When a doctor works at one clinic, on one weekday (docs/15, D7).

    One row per doctor, clinic and weekday, with at most one break — the weekly
    pattern the online booking offers times from. A doctor who works at two
    clinics has rows for each; a weekday with no row is a day off there.
    `weekday` follows Python: Monday 0 … Sunday 6.
    """

    doctor = models.ForeignKey(
        "employees.Employee", on_delete=models.CASCADE, related_name="schedules",
        limit_choices_to={"employee_type__name": "Doctor"},
    )
    branch = models.ForeignKey("branches.Branch", on_delete=models.CASCADE, related_name="doctor_schedules")
    weekday = models.PositiveSmallIntegerField(validators=[MaxValueValidator(6)])
    start_time = models.TimeField()
    end_time = models.TimeField()
    break_start = models.TimeField(null=True, blank=True)
    break_end = models.TimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "doctor", "branch", "weekday"], name="uniq_schedule_per_day"
            ),
            models.CheckConstraint(condition=models.Q(end_time__gt=models.F("start_time")), name="schedule_ends_after_start"),
            # A break is both ends or neither, and inside the working hours.
            models.CheckConstraint(
                condition=(
                    models.Q(break_start__isnull=True, break_end__isnull=True)
                    | models.Q(
                        break_start__isnull=False, break_end__isnull=False,
                        break_end__gt=models.F("break_start"),
                        break_start__gte=models.F("start_time"), break_end__lte=models.F("end_time"),
                    )
                ),
                name="schedule_break_inside_hours",
            ),
        ]
        indexes = [models.Index(fields=["tenant", "branch", "weekday"], name="schedule_branch_day_idx")]

    def __str__(self):
        return f"{self.doctor_id}@{self.branch_id} d{self.weekday} {self.start_time}-{self.end_time}"


class DoctorTimeOff(TenantOwnedModel):
    """Days a doctor is away (leave, a conference): no online times are offered
    at any clinic. `reason` is internal — never shown to the public."""

    doctor = models.ForeignKey(
        "employees.Employee", on_delete=models.CASCADE, related_name="time_off",
        limit_choices_to={"employee_type__name": "Doctor"},
    )
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.CharField(max_length=200, blank=True, default="")

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.CheckConstraint(condition=models.Q(end_date__gte=models.F("start_date")), name="timeoff_ends_after_start"),
        ]
        indexes = [models.Index(fields=["tenant", "doctor", "start_date"], name="timeoff_doctor_start_idx")]


class BranchHoliday(TenantOwnedModel):
    """A day (or run of days) a clinic is closed. With no clinic it closes the
    whole group (a public holiday) — the Owner's to set."""

    branch = models.ForeignKey(
        "branches.Branch", on_delete=models.CASCADE, null=True, blank=True, related_name="holidays"
    )
    start_date = models.DateField()
    end_date = models.DateField()
    name = models.CharField(max_length=150, blank=True, default="")

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.CheckConstraint(condition=models.Q(end_date__gte=models.F("start_date")), name="holiday_ends_after_start"),
        ]
        indexes = [models.Index(fields=["tenant", "start_date"], name="holiday_start_idx")]
