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
