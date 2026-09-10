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
