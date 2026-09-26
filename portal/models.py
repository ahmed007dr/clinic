"""The patient portal's own identities — deliberately not `accounts.User`.

A patient `User` would carry a tenant, and `TenantMiddleware` plus
`IsClinicMember` admit any authenticated user with a tenant: one forgotten role
check and a patient is reading `/api/patients/`. So patients get their own
account, their own session and their own cookie, and the two worlds never meet
(docs/12, section 1).

All three models are tenant-owned, so row-level security applies to them like
everything else: a portal request looks them up only after entering the
clinic's `tenant_context`, and a token from clinic X is simply not found under
clinic Y.

Tokens — invitations and sessions — are stored **hashed**, like passwords. A
database read, a backup or a log line never yields a usable credential.
"""

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.utils import timezone

from tenants.models import TenantOwnedModel

INVITATION_TTL = timedelta(hours=72)
SESSION_IDLE = timedelta(minutes=30)
SESSION_ABSOLUTE = timedelta(days=7)
MAX_FAILED_LOGINS = 5
LOCKOUT = timedelta(minutes=15)
CODE_TTL = timedelta(minutes=10)
CODE_RESEND_AFTER = timedelta(seconds=60)
CODE_MAX_ATTEMPTS = 5


def new_token():
    """URL-safe, 32 bytes of entropy."""
    return secrets.token_urlsafe(32)


def hash_token(token):
    # SHA-256 rather than a slow password hash: the token is 256 random bits,
    # so there is nothing to brute-force, and it is checked on every request.
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class PatientAccount(TenantOwnedModel):
    """A patient's portal login. One per patient."""

    patient = models.OneToOneField(
        "patients.Patient", on_delete=models.CASCADE, related_name="portal_account"
    )
    password = models.CharField(max_length=128, blank=True)
    is_active = models.BooleanField(default=True)
    failed_logins = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_login = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantOwnedModel.Meta):
        verbose_name = "حساب بوابة"

    def set_password(self, raw):
        self.password = make_password(raw)

    def check_password(self, raw):
        return bool(self.password) and check_password(raw, self.password)

    @property
    def is_locked(self):
        return bool(self.locked_until and self.locked_until > timezone.now())

    def register_failure(self):
        self.failed_logins += 1
        if self.failed_logins >= MAX_FAILED_LOGINS:
            self.locked_until = timezone.now() + LOCKOUT
            self.failed_logins = 0
        self.save(update_fields=["failed_logins", "locked_until"])

    def revoke_sessions(self):
        PortalSession.objects.filter(account=self, revoked_at__isnull=True).update(
            revoked_at=timezone.now()
        )


def new_code():
    """Six digits, from the OS entropy pool."""
    return f"{secrets.randbelow(10**6):06d}"


class PortalLoginCode(TenantOwnedModel):
    """A one-time sign-in code emailed to the patient (docs/12, Phase 2).

    Stored hashed, like every portal credential. It lives ten minutes, works
    once, and is voided after five wrong guesses — six digits alone would not
    survive an attacker who could guess without limit.
    """

    account = models.ForeignKey(PatientAccount, on_delete=models.CASCADE, related_name="login_codes")
    code_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantOwnedModel.Meta):
        verbose_name = "رمز دخول بوابة"

    @classmethod
    def issue(cls, account):
        """Returns (row, code), or (None, None) if one was sent under a
        minute ago. A new code voids any earlier unused one."""
        recent = cls.objects.filter(
            account=account, created_at__gt=timezone.now() - CODE_RESEND_AFTER
        ).exists()
        if recent:
            return None, None
        cls.objects.filter(account=account, used_at__isnull=True).update(used_at=timezone.now())
        code = new_code()
        row = cls.objects.create(
            tenant=account.tenant, account=account, code_hash=hash_token(code),
            expires_at=timezone.now() + CODE_TTL,
        )
        return row, code

    @property
    def is_usable(self):
        return (
            self.used_at is None
            and self.expires_at > timezone.now()
            and self.attempts < CODE_MAX_ATTEMPTS
        )

    def verify(self, code):
        """True once, for the right code. A wrong guess is counted."""
        if not self.is_usable:
            return False
        if secrets.compare_digest(self.code_hash, hash_token(str(code).strip())):
            self.used_at = timezone.now()
            self.save(update_fields=["used_at"])
            return True
        self.attempts += 1
        self.save(update_fields=["attempts"])
        return False


class PortalInvitation(TenantOwnedModel):
    """A single-use link a clinic hands a patient to set their password."""

    patient = models.ForeignKey(
        "patients.Patient", on_delete=models.CASCADE, related_name="portal_invitations"
    )
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantOwnedModel.Meta):
        verbose_name = "دعوة بوابة"

    @classmethod
    def issue(cls, patient, created_by=None):
        """Returns (invitation, token). The token exists only in this return
        value — it is never stored — so it must be shown to staff now."""
        token = new_token()
        # A fresh invitation supersedes any earlier unused one: only the link
        # most recently handed over should work.
        cls.objects.filter(patient=patient, used_at__isnull=True).update(
            used_at=timezone.now()
        )
        invitation = cls.objects.create(
            tenant=patient.tenant,
            patient=patient,
            token_hash=hash_token(token),
            expires_at=timezone.now() + INVITATION_TTL,
            created_by=created_by,
        )
        return invitation, token

    @property
    def is_usable(self):
        return self.used_at is None and self.expires_at > timezone.now()


class PortalSession(TenantOwnedModel):
    """A signed-in portal session. Server-side, so staff can end it."""

    account = models.ForeignKey(
        PatientAccount, on_delete=models.CASCADE, related_name="sessions"
    )
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(default=timezone.now)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantOwnedModel.Meta):
        verbose_name = "جلسة بوابة"

    @classmethod
    def start(cls, account):
        token = new_token()
        cls.objects.create(tenant=account.tenant, account=account, token_hash=hash_token(token))
        return token

    @property
    def is_live(self):
        now = timezone.now()
        return (
            self.revoked_at is None
            and now - self.last_seen < SESSION_IDLE
            and now - self.created_at < SESSION_ABSOLUTE
        )


class PortalVerification(TenantOwnedModel):
    """A pending step that needs proof the person controls an e-mail address:
    creating a portal account, or changing the e-mail on one (docs/15, D5).

    The details the person typed wait here — never in the browser, never in a
    Patient row — until the right code comes back. Like every portal
    credential the code and the ticket are stored **hashed**. The ticket is the
    opaque handle the browser holds between the two steps; the code is what
    travels by the channel. Ten minutes, five guesses, once.
    """

    class Purpose(models.TextChoices):
        SIGNUP = "signup", "إنشاء حساب"
        EMAIL_CHANGE = "email_change", "تغيير البريد"

    purpose = models.CharField(max_length=20, choices=Purpose.choices)
    ticket_hash = models.CharField(max_length=64, unique=True)
    code_hash = models.CharField(max_length=64)
    channel = models.CharField(max_length=20, default="email")
    #: What was submitted (a signup's fields incl. the hashed password; the new
    #: address of an e-mail change). Never a plain-text secret.
    data = models.JSONField(default=dict)
    #: The existing patient a signup will be linked to, or whose e-mail is changing.
    patient = models.ForeignKey(
        "patients.Patient", on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantOwnedModel.Meta):
        verbose_name = "تحقق بوابة"
        indexes = [models.Index(fields=["tenant", "created_at"], name="portal_verif_created_idx")]

    @classmethod
    def issue(cls, *, tenant, purpose, data, patient=None, channel="email"):
        """Returns (row, ticket, code). The ticket and the code exist only in
        this return value."""
        ticket, code = new_token(), new_code()
        row = cls.objects.create(
            tenant=tenant, purpose=purpose, data=data, patient=patient, channel=channel,
            ticket_hash=hash_token(ticket), code_hash=hash_token(code),
            expires_at=timezone.now() + CODE_TTL,
        )
        return row, ticket, code

    @classmethod
    def recent_count(cls, *, purpose, key, key_value, within=timedelta(hours=1)):
        """How many were issued lately for the same `data[key]` — the limit
        that stops one address being flooded with codes."""
        since = timezone.now() - within
        return sum(
            1 for row in cls.objects.filter(purpose=purpose, created_at__gt=since)
            if row.data.get(key) == key_value
        )

    @property
    def is_usable(self):
        return (
            self.used_at is None
            and self.expires_at > timezone.now()
            and self.attempts < CODE_MAX_ATTEMPTS
        )

    def verify(self, code):
        """True once, for the right code. A wrong guess is counted."""
        if not self.is_usable:
            return False
        if secrets.compare_digest(self.code_hash, hash_token(str(code).strip())):
            self.used_at = timezone.now()
            self.save(update_fields=["used_at"])
            return True
        self.attempts += 1
        self.save(update_fields=["attempts"])
        return False


# --------------------------------------------------------------- service orders


class ServiceOrder(TenantOwnedModel):
    """What a customer asks a clinic for from the website (docs/16).

    A customer puts services into «طلباتي» — a service, the clinic that offers
    it, a quantity where the service is sold by quantity — and sends the order.
    It is **one order per clinic**: a basket with lines for two clinics becomes
    two orders, each decided by its own clinic. It holds no doctor's time. The
    clinic's Admin approves (or refuses) it, the clinic's customer service phones
    the customer, and only then is the doctor and the time settled — at which
    point real bookings (`Appointment`) are created and everything downstream
    (queue, shifts, payments) works as it always has.
    """

    class Status(models.TextChoices):
        SUBMITTED = "submitted", "بانتظار موافقة العيادة"
        APPROVED = "approved", "وافقت العيادة — بانتظار اتصال خدمة العملاء"
        CONTACTED = "contacted", "تم الاتصال بك"
        SCHEDULED = "scheduled", "تم تحديد الموعد"
        REJECTED = "rejected", "لم توافق العيادة"
        CANCELLED = "cancelled", "ألغيته"

    #: Still open: the clinic has not finished with it, and the customer may withdraw it.
    OPEN = (Status.SUBMITTED, Status.APPROVED, Status.CONTACTED)

    patient = models.ForeignKey("patients.Patient", on_delete=models.CASCADE, related_name="service_orders")
    branch = models.ForeignKey("branches.Branch", on_delete=models.CASCADE, related_name="service_orders")
    serial_number = models.CharField(max_length=24, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.SUBMITTED)
    class Payment(models.TextChoices):
        ONLINE = "online", "أونلاين"
        MANUAL = "manual", "يدوي: تحويل أو عند الوصول"

    #: How the customer says they will pay. Only a preference: the money is recorded,
    #: inside a shift, against the bookings the order becomes (docs/16, R3).
    payment_preference = models.CharField(max_length=8, choices=Payment.choices, default=Payment.MANUAL)
    # The customer's words; a few of each, never trusted as markup.
    notes = models.CharField(max_length=1000, blank=True, default="")
    preferred_contact = models.CharField(max_length=100, blank=True, default="")
    # The clinic's Admin's decision.
    reviewed_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=300, blank=True, default="")
    # Customer service's call.
    contacted_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    contacted_at = models.DateTimeField(null=True, blank=True)
    contact_note = models.CharField(max_length=300, blank=True, default="")
    # Who settled the doctor and time, and when.
    scheduled_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    scheduled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "serial_number"], name="uniq_service_order_serial")
        ]
        indexes = [models.Index(fields=["tenant", "branch", "status"], name="serviceorder_branch_status_idx")]

    def save(self, *args, **kwargs):
        if not self.serial_number:
            from tenants.models import SerialCounter

            day = (self.created_at or timezone.now()).date()
            self.serial_number = "SO-" + SerialCounter.next_serial(self.tenant_id, "service_order", day)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.serial_number

    @property
    def is_open(self):
        return self.status in self.OPEN


class ServiceOrderLine(TenantOwnedModel):
    """One service in an order. The figures are what the customer was shown when
    they sent it; the service's name is kept too, so the order still reads the
    same if the service is later renamed."""

    order = models.ForeignKey(ServiceOrder, on_delete=models.CASCADE, related_name="lines")
    service = models.ForeignKey("services.Service", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    service_name = models.CharField(max_length=150)
    quantity = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    quantity_unit = models.CharField(max_length=30, blank=True, default="")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # False when the price is only "from": it depends on the doctor, on the
    # quantity the doctor sets, or on an evaluation. The doctor's own price
    # settles it when the booking is made.
    price_is_final = models.BooleanField(default=True)
    # What the customer picked from the times on offer (docs/16, R2): a preference —
    # it holds no time — which the clinic confirms or changes when it settles the order.
    preferred_doctor = models.ForeignKey("employees.Employee", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    preferred_at = models.DateTimeField(null=True, blank=True)
    # The booking made from this line once the time is settled.
    appointment = models.ForeignKey("appointments.Appointment", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta(TenantOwnedModel.Meta):
        ordering = ["id"]

    def __str__(self):
        return f"{self.order_id}:{self.service_name}"
