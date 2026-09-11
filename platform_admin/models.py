"""The platform's own records — not any clinic's.

Everything here belongs to the platform operator: the keys and passwords of
integrations, what each owner group has agreed to pay, the invoices and
payments of that agreement, requests to open a clinic, mailboxes created for
groups, and backups. None of it is clinic data, so none of it carries a
`tenant` field: the row-level security derivation (tenants/rls.py) covers
models with a non-nullable `tenant`, and these point at their customer as
`customer` on purpose — the platform reads across customers, and the clinic
side reaches its own rows only through endpoints that filter to it.
"""

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from tenants.models import Tenant


class IntegrationCredential(models.Model):
    """Keys and passwords for one integration, for one scope.

    Entered only in the developer portal, never in files (the group owner's
    rule, 2026-09-11). Each has a **test** and a **production** set, and `mode`
    says which one is live. Secrets are encrypted at rest (platform_admin/vault.py)
    and never sent back to the browser whole.

    Scope, most specific first when resolving: one clinic (branch), one owner
    group, or the whole platform.
    """

    class Kind(models.TextChoices):
        SMTP = "smtp", "بريد إلكتروني (SMTP)"
        CPANEL = "cpanel", "cPanel (إنشاء الإيميلات)"
        PAYMOB = "paymob", "Paymob"
        FAWRY = "fawry", "Fawry"
        VODAFONE_CASH = "vodafone_cash", "فودافون كاش"
        GOOGLE_DRIVE = "google_drive", "Google Drive (النسخ الاحتياطي)"

    class Scope(models.TextChoices):
        PLATFORM = "platform", "المنصة"
        GROUP = "group", "مجموعة (أونر)"
        CLINIC = "clinic", "عيادة"

    class Mode(models.TextChoices):
        TEST = "test", "تجريبي"
        PRODUCTION = "production", "إنتاج"

    kind = models.CharField(max_length=20, choices=Kind.choices)
    scope = models.CharField(max_length=10, choices=Scope.choices)
    customer = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True, related_name="+")
    branch = models.ForeignKey("branches.Branch", on_delete=models.CASCADE, null=True, blank=True, related_name="+")
    mode = models.CharField(max_length=10, choices=Mode.choices, default=Mode.TEST)
    enabled = models.BooleanField(default=True)
    #: Encrypted JSON of each environment's settings (vault.seal / vault.open).
    test_config = models.TextField(blank=True, default="")
    production_config = models.TextField(blank=True, default="")
    notes = models.CharField(max_length=300, blank=True, default="")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["kind", "scope", "customer", "branch"], name="one_credential_per_kind_and_scope",
            ),
        ]
        ordering = ["kind", "scope"]

    def __str__(self):
        return f"{self.kind} · {self.scope}"


class Mailbox(models.Model):
    """An email account created on the platform's cPanel for an owner group or
    one of its clinics (platform_admin/mailboxes.py)."""

    customer = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="+")
    branch = models.ForeignKey("branches.Branch", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    address = models.EmailField(unique=True)
    quota_mb = models.PositiveIntegerField(default=1024)
    #: Whether its SMTP settings were stored as the group's/clinic's sender.
    used_for_sending = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.address


# ------------------------------------------------------------ the business


class CommercialTerms(models.Model):
    """What one owner group has agreed to pay: its cycle and, when negotiated,
    its own price. Without a custom price the plan's price applies (twelve
    months of it for a yearly cycle, unless the plan is itself yearly)."""

    class Cycle(models.TextChoices):
        MONTHLY = "monthly", "شهري"
        YEARLY = "yearly", "سنوي"

    customer = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name="commercial_terms")
    cycle = models.CharField(max_length=10, choices=Cycle.choices, default=Cycle.MONTHLY)
    custom_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)]
    )
    currency = models.CharField(max_length=3, default="EGP")
    #: When the next invoice is due to be issued (platform_admin/billing.py).
    next_invoice_on = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.customer} · {self.cycle}"


class Discount(models.Model):
    """A discount for a limited period: a percentage, a fixed amount, or both
    (the percentage first, then the amount). Applies to invoices whose period
    starts inside [starts_on, ends_on]."""

    customer = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="+")
    percent = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)]
    )
    starts_on = models.DateField()
    ends_on = models.DateField()
    reason = models.CharField(max_length=200, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-starts_on"]
        constraints = [
            models.CheckConstraint(condition=models.Q(ends_on__gte=models.F("starts_on")), name="discount_ends_after_start"),
            models.CheckConstraint(
                condition=models.Q(percent__isnull=False) | models.Q(amount__isnull=False),
                name="discount_has_a_value",
            ),
        ]


class PlatformInvoice(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "مستحقة"
        PARTIAL = "partial", "مدفوعة جزئياً"
        PAID = "paid", "مدفوعة"
        VOID = "void", "ملغاة"

    customer = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="+")
    number = models.CharField(max_length=20, unique=True)
    period_start = models.DateField()
    period_end = models.DateField()
    description = models.CharField(max_length=200)
    base_amount = models.DecimalField(max_digits=10, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="EGP")
    due_on = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    notes = models.CharField(max_length=300, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-period_start", "-id"]

    def __str__(self):
        return self.number


class PlatformPayment(models.Model):
    """Money received from an owner group — recorded by hand (cash, bank
    transfer) or confirmed by a gateway's callback (Paymob, Fawry, Vodafone
    Cash; platform_admin/gateways.py)."""

    class Method(models.TextChoices):
        CASH = "cash", "نقدي"
        TRANSFER = "transfer", "تحويل بنكي"
        PAYMOB = "paymob", "Paymob"
        FAWRY = "fawry", "Fawry"
        VODAFONE_CASH = "vodafone_cash", "فودافون كاش"

    class Status(models.TextChoices):
        PENDING = "pending", "بانتظار التأكيد"
        CONFIRMED = "confirmed", "مؤكد"
        FAILED = "failed", "فشل"

    customer = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="+")
    invoice = models.ForeignKey(PlatformInvoice, on_delete=models.SET_NULL, null=True, blank=True, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    method = models.CharField(max_length=20, choices=Method.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.CONFIRMED)
    reference = models.CharField(max_length=120, blank=True, default="")
    mode = models.CharField(max_length=10, blank=True, default="", help_text="Gateway environment: test or production.")
    gateway_payload = models.JSONField(default=dict, blank=True)
    paid_at = models.DateTimeField()
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-paid_at", "-id"]


class LateNote(models.Model):
    """A late payment, recorded by the operator (not by a fixed rule — the
    group owner's decision, 2026-09-11)."""

    customer = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="+")
    note = models.CharField(max_length=300)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class ClinicCheckout(models.Model):
    """A patient paying a clinic online, with the clinic's (or its group's)
    own gateway keys — never the platform's (vault.resolve with
    include_platform=False).

    Kept on the platform side because the gateway's callback arrives with no
    clinic bound: this row says which clinic, so the confirmed money can be
    written inside that clinic's context as an ordinary `billing.Payment`
    (platform_admin/clinic_pay.py).
    """

    class Status(models.TextChoices):
        PENDING = "pending", "بانتظار الدفع"
        CONFIRMED = "confirmed", "مدفوع"
        FAILED = "failed", "فشل"

    customer = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="+")
    branch_id = models.BigIntegerField(null=True, blank=True)
    appointment_uuid = models.UUIDField()
    patient_id = models.BigIntegerField()
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    method = models.CharField(max_length=20)
    mode = models.CharField(max_length=10)
    credential = models.ForeignKey(IntegrationCredential, on_delete=models.PROTECT, related_name="+")
    reference = models.CharField(max_length=60, unique=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    gateway_id = models.CharField(max_length=80, blank=True, default="")
    #: The clinic payment it became, once confirmed.
    payment_uuid = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.reference


class SignupRequest(models.Model):
    """Someone asking to open a clinic group, from the public form
    (`/app/signup`). The developer approves it — which onboards the group
    exactly as the portal's own form does (platform_admin/onboarding.py) — or
    rejects it with a reason."""

    class Status(models.TextChoices):
        PENDING = "pending", "بانتظار المراجعة"
        APPROVED = "approved", "تمت الموافقة"
        REJECTED = "rejected", "مرفوض"

    group_name = models.CharField(max_length=150)
    clinic_name = models.CharField(max_length=150, blank=True, default="")
    owner_name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=32)
    city = models.CharField(max_length=80, blank=True, default="")
    specialty = models.CharField(max_length=120, blank=True, default="")
    branches = models.PositiveSmallIntegerField(default=1)
    doctors = models.PositiveSmallIntegerField(default=1)
    plan = models.ForeignKey("subscriptions.Plan", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    cycle = models.CharField(max_length=10, choices=CommercialTerms.Cycle.choices, default=CommercialTerms.Cycle.MONTHLY)
    message = models.TextField(blank=True, default="")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    reject_reason = models.CharField(max_length=300, blank=True, default="")
    #: The group it became, once approved. `customer`, not `tenant`, like
    #: every platform record (see the module docstring).
    customer = models.ForeignKey(Tenant, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    handled_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.group_name} <{self.email}>"


class SupportSession(models.Model):
    """A developer signed in as one of a group's accounts ("login as"), for
    support — time-limited, with a reason, recorded here and in the group's
    audit trail, and announced to the group's owners
    (platform_admin/impersonation.py)."""

    operator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    customer = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="+")
    target = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    reason = models.CharField(max_length=300)
    started_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]


class BackupPolicy(models.Model):
    """How backups are kept — one row, edited in the developer portal
    (platform_admin/backups.py). The Google Drive keys are an integration
    like any other (vault kind `google_drive`)."""

    keep_local = models.PositiveSmallIntegerField(default=14)
    upload_to_drive = models.BooleanField(default=True)
    keep_drive = models.PositiveSmallIntegerField(default=30)
    include_files = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def current(cls):
        return cls.objects.order_by("pk").first() or cls.objects.create()


class BackupRun(models.Model):
    """One backup: an encrypted archive on the server, and its copy on
    Google Drive when that is configured."""

    class Status(models.TextChoices):
        RUNNING = "running", "جارٍ"
        DONE = "done", "تم"
        FAILED = "failed", "فشل"

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RUNNING)
    file_name = models.CharField(max_length=120, blank=True, default="")
    size = models.BigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True, default="")
    groups = models.PositiveIntegerField(default=0)
    drive_file_id = models.CharField(max_length=120, blank=True, default="")
    drive_error = models.CharField(max_length=300, blank=True, default="")
    error = models.TextField(blank=True, default="")
    trigger = models.CharField(max_length=10, default="manual")  # manual | schedule
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
