# accounts/models.py
import uuid

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.validators import UnicodeUsernameValidator
from branches.models import Branch
from tenants.models import Tenant, TenantOwnedModel

class ClinicRole(TenantOwnedModel):
    name = models.CharField(max_length=50)
    description = models.TextField(blank=True, null=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="uniq_clinicrole_name_per_tenant")
        ]

    def __str__(self):
        return self.name

class User(AbstractUser):
    # Null only for platform staff (SaaS operators), who legitimately span tenants.
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="+", null=True, blank=True)

    # Public identifier — see TenantOwnedModel.uuid.
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    # Email is the login: it is the one identifier that stays unique across the
    # whole platform, which lets usernames repeat between clinics.
    email = models.EmailField("email address", unique=True)

    # Username survives as a display name, unique only within a tenant, so two
    # clinics can both have a "reception" account.
    username = models.CharField(
        max_length=150,
        validators=[UnicodeUsernameValidator()],
        help_text="150 characters or fewer. Letters, digits and @/./+/-/_ only.",
    )

    # Platform staff (support, operators) span tenants and so carry no tenant of
    # their own. They get no implicit access: the tenant-scoped manager returns
    # nothing for them, and reaching across tenants stays an explicit, named act.
    is_platform_staff = models.BooleanField(
        default=False,
        help_text="SaaS operator rather than a member of any one clinic.",
    )

    clinic_code = models.CharField(max_length=20)
    role = models.ForeignKey(ClinicRole, on_delete=models.SET_NULL, null=True, blank=True)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True)
    # Which doctor this login *is*. Visits, bookings and prescriptions name an
    # Employee, not a User, so without this a doctor's account could not be
    # told apart from any other doctor's — and "a doctor sees their own
    # patients" had nothing to filter on. One account per doctor.
    employee = models.OneToOneField(
        "employees.Employee", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="user_account",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "username"], name="uniq_username_per_tenant")
        ]

    def __str__(self):
        return f"{self.username} ({self.role})"

    @property
    def unread_notifications(self):
        try:
            return self.notifications.filter(is_read=False)
        except Exception:
            return []
