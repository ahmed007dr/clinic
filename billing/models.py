# billing/models.py
from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from patients.models import Patient
from appointments.models import Appointment
from branches.models import Branch
from employees.models import Employee  
from django.conf import settings
from tenants.models import TenantManager, TenantOwnedModel


class LiveTenantManager(TenantManager):
    """The tenant's rows that still count — voided ones left out.

    A voided payment or expense stays in the database (who cancelled it, when
    and why is the point), but it is money that did not happen, so every sum,
    report, list and related manager built on `objects` simply does not see
    it. Management reviews voided rows through `with_voided()`.
    """

    def get_queryset(self):
        return super().get_queryset().filter(voided_at__isnull=True)

    def with_voided(self):
        return super().get_queryset()



class PaymentMethod(TenantOwnedModel):
    name = models.CharField(max_length=50)  # Cash, Visa, Insurance, etc
    description = models.TextField(blank=True, null=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="uniq_paymentmethod_name_per_tenant")
        ]

    def __str__(self):
        return self.name


class CashShift(TenantOwnedModel):
    """One person's cash drawer, from opening to closing.

    Money is taken at a desk by a named person, and the question every clinic
    asks at the end of a day is "what did *you* take, and does the drawer
    agree?". So a shift belongs to one user — a receptionist or a clinic Admin
    — and every payment or expense they record is filed under it
    (billing.shifts). The Owner records outside shifts.

    * Opened by the person themselves, with the cash already in the drawer.
    * Closed by them at the end of their day, or by management. Once closed,
      the person who ran it can no longer see it or anything in it: a shift's
      figures, and everyone else's, are management's to review
      (billing.access).
    * Reopened only by an Admin or the Owner.

    `closing_summary` is the per-method breakdown frozen at the moment of
    closing, so a later correction to a payment is visible as a difference
    from what was handed over, not silently folded into it.
    """

    class Status(models.TextChoices):
        OPEN = "open", "مفتوحة"
        CLOSED = "closed", "مغلقة"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cash_shifts"
    )
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="cash_shifts")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    opening_balance = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)]
    )
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )
    closing_summary = models.JSONField(null=True, blank=True)
    reopened_at = models.DateTimeField(null=True, blank=True)
    reopened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )
    notes = models.TextField(blank=True, default="")

    class Meta(TenantOwnedModel.Meta):
        ordering = ["-opened_at"]
        constraints = [
            # One drawer at a time per person: two open shifts would leave it
            # ambiguous which one a payment belongs to.
            models.UniqueConstraint(
                fields=["tenant", "user"], condition=models.Q(status="open"),
                name="one_open_shift_per_user",
            )
        ]
        indexes = [models.Index(fields=["tenant", "branch", "opened_at"], name="shift_branch_opened_idx")]

    def __str__(self):
        return f"Shift {self.user} {self.opened_at:%Y-%m-%d}"

    @property
    def is_open(self):
        return self.status == self.Status.OPEN


class Payment(TenantOwnedModel):
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name="payments")
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    method = models.ForeignKey(PaymentMethod, on_delete=models.SET_NULL, null=True)
    receipt_number = models.CharField(max_length=50)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True)
    date = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)
    # The drawer it went into. Null for payments from before shifts existed
    # and for ones the Owner records.
    shift = models.ForeignKey(
        CashShift, on_delete=models.PROTECT, null=True, blank=True, related_name="payments"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )
    # Voided (billing.voiding): cancelled by management with a reason, kept
    # on record, and out of every total — the default manager hides it.
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )
    void_reason = models.CharField(max_length=300, blank=True, default="")

    objects = LiveTenantManager()
    all_objects = models.Manager()

    class Meta(TenantOwnedModel.Meta):
        default_manager_name = "objects"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "receipt_number"], name="uniq_payment_receipt_per_tenant")
        ]
        # Every revenue report is a date range, usually per clinic.
        indexes = [models.Index(fields=["tenant", "branch", "date"], name="payment_branch_date_idx")]

    def __str__(self):
        return f"Payment {self.receipt_number} - {self.amount} EGP"


class ExpenseCategory(TenantOwnedModel):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="uniq_expensecategory_name_per_tenant")
        ]

    def __str__(self):
        return self.name


class Expense(TenantOwnedModel):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="expenses")
    category = models.ForeignKey(ExpenseCategory, on_delete=models.SET_NULL, null=True, blank=True)

    employee = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name="expenses")

    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    date = models.DateField()
    # Paid out how — the shift's closing report nets each method's takings
    # against what left by the same method.
    method = models.ForeignKey(
        PaymentMethod, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    shift = models.ForeignKey(
        CashShift, on_delete=models.PROTECT, null=True, blank=True, related_name="expenses"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    notes = models.TextField(blank=True, null=True)
    # Voided (billing.voiding): cancelled by management with a reason, kept
    # on record, and out of every total — the default manager hides it.
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )
    void_reason = models.CharField(max_length=300, blank=True, default="")

    objects = LiveTenantManager()
    all_objects = models.Manager()

    class Meta(TenantOwnedModel.Meta):
        default_manager_name = "objects"
        indexes = [models.Index(fields=["tenant", "branch", "date"], name="expense_branch_date_idx")]

    def __str__(self):
        return f"{self.category.name if self.category else 'غير محدد'} - {self.amount}"


class DoctorServiceRate(TenantOwnedModel):
    """One line of a doctor's contract with the group: for this service, this
    price, and this share for the doctor.

    Set by management only (the group owner's rule, 2026-09-11) — a doctor
    never sets a price. Both figures are optional: no price here means the
    service's catalogue price; no percentage means the doctor's default
    (`Employee.commission_percent`). A change applies from then on — every
    booking and commission copies the figures it was made with (billing.pricing,
    billing.commissions), so editing a contract never rewrites the past.
    """

    doctor = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="service_rates",
        limit_choices_to={"employee_type__name": "Doctor"},
    )
    service = models.ForeignKey("services.Service", on_delete=models.CASCADE, related_name="doctor_rates")
    price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)]
    )
    commission_percent = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    is_active = models.BooleanField(default=True)
    notes = models.CharField(max_length=200, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "doctor", "service"], name="uniq_rate_per_doctor_service")
        ]

    def __str__(self):
        return f"{self.doctor} · {self.service}"


class DoctorCommission(TenantOwnedModel):
    """The doctor's share of one payment actually received.

    Computed on the amount paid, not the price (the group owner's rule):
    `amount = paid_amount × percent / 100`. The service, its original price
    and the percentage are copied in when it is created, so a later change to
    a contract or a price list leaves it as it was earned. Management marks it
    received (settled); until then it is pending. The doctor sees their own,
    and nothing else of the clinic's money (billing.access).
    """

    class Status(models.TextChoices):
        PENDING = "pending", "معلّقة"
        SETTLED = "settled", "مستلمة"

    doctor = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="commissions")
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True)
    # SET_NULL: a settled share was handed over, and stays on record even if
    # the payment behind it is later removed.
    payment = models.OneToOneField(
        Payment, on_delete=models.SET_NULL, null=True, blank=True, related_name="commission"
    )
    appointment = models.ForeignKey(Appointment, on_delete=models.SET_NULL, null=True, blank=True)
    patient = models.ForeignKey(Patient, on_delete=models.SET_NULL, null=True, blank=True)
    service = models.ForeignKey("services.Service", on_delete=models.SET_NULL, null=True, blank=True)
    description = models.CharField(max_length=200, blank=True, default="")
    original_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    percent = models.DecimalField(max_digits=5, decimal_places=2)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    settled_at = models.DateTimeField(null=True, blank=True)
    settled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta(TenantOwnedModel.Meta):
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["tenant", "doctor", "status"], name="commission_doctor_status_idx")]

    def __str__(self):
        return f"{self.doctor} {self.amount} ({self.status})"
