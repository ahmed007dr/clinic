"""Everything a new tenant needs before it can be used.

Single source of truth for tenant setup: the post_migrate hook calls it for
existing tenants, the demo seeder calls it, and tenant onboarding (TENANT-008)
will call the same function rather than reinventing the list.
"""

from django.utils.crypto import get_random_string
from django.utils.text import slugify

# Ambiguous characters left out — these get read off a screen and typed by hand.
PASSWORD_ALPHABET = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"

DEFAULT_ROLES = [
    ("Admin", "System administrator"),
    ("Reception", "Reception staff"),
    # Clinical access is granted by role. Without this, a clinic has no account
    # that can record a diagnosis — see medical/permissions.py.
    ("Doctor", "Clinician — may read and write medical records"),
]

# Appointment.doctor filters on employee_type__name="Doctor" via
# limit_choices_to, so a tenant without this row cannot book with a doctor.
DEFAULT_EMPLOYEE_TYPES = [
    ("Doctor", "Medical Doctor"),
]


def provision_tenant_defaults(tenant):
    """Idempotent — safe to run against a tenant that already has its rows."""
    from accounts.models import ClinicRole
    from employees.models import EmployeeType

    for name, description in DEFAULT_ROLES:
        ClinicRole.all_objects.get_or_create(
            tenant=tenant, name=name, defaults={"description": description}
        )

    for name, description in DEFAULT_EMPLOYEE_TYPES:
        EmployeeType.all_objects.get_or_create(
            tenant=tenant, name=name, defaults={"description": description}
        )

    return tenant


def create_tenant(name, slug=None, status=None):
    """Create a tenant and seed it in one step."""
    from .models import Tenant

    tenant = Tenant.objects.create(
        name=name,
        slug=slug or slugify(name),
        status=status or Tenant.Status.TRIAL,
    )
    return provision_tenant_defaults(tenant)


def create_first_branch(tenant, name, code=None):
    """A tenant with no branch cannot take a booking — staff, patients and
    appointments all hang off one."""
    from branches.models import Branch

    # slugify() returns "" for Arabic names, so fall back rather than blank.
    fallback = slugify(name).upper()[:20] or "MAIN"
    return Branch.all_objects.create(tenant=tenant, name=name, code=code or fallback)


def create_tenant_admin(tenant, email, password=None, username="admin", branch=None):
    """The tenant's first user. Without one, nobody can log in to it.

    Returns (user, password). A generated password is returned so the caller
    can show it once — it is not stored anywhere in readable form.
    """
    from django.contrib.auth import get_user_model

    from accounts.models import ClinicRole

    User = get_user_model()

    if password is None:
        password = get_random_string(14, allowed_chars=PASSWORD_ALPHABET)

    # provision_tenant_defaults guarantees this exists.
    admin_role = ClinicRole.all_objects.get(tenant=tenant, name="Admin")

    user = User.objects.create_user(
        username=username,
        email=email,
        password=password,
        tenant=tenant,
        role=admin_role,
        branch=branch,
        clinic_code=tenant.slug.upper()[:20],
    )
    return user, password
