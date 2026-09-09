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
    """Idempotent — safe to run against a tenant that already has its rows.

    Runs inside tenant_context because these rows are tenant-owned: under
    PostgreSQL row-level security an INSERT is rejected unless the connection
    has declared which tenant it is acting for.
    """
    from accounts.models import ClinicRole
    from employees.models import EmployeeType

    from .context import tenant_context

    with tenant_context(tenant):
        for name, description in DEFAULT_ROLES:
            ClinicRole.all_objects.get_or_create(
                tenant=tenant, name=name, defaults={"description": description}
            )

        for name, description in DEFAULT_EMPLOYEE_TYPES:
            EmployeeType.all_objects.get_or_create(
                tenant=tenant, name=name, defaults={"description": description}
            )

        ensure_subscription(tenant)

    return tenant


# A new clinic starts on the entry tier, on trial. Not "no subscription":
# entitlements fail closed, so a tenant without one has a zero branch limit and
# cannot finish its own setup.
DEFAULT_PLAN_CODE = "basic"
TRIAL_DAYS = 30


def ensure_subscription(tenant):
    """Give a tenant a subscription if it has none. Idempotent, and it never
    replaces an existing active one — a tenant that has been moved onto another
    plan must not be silently reset by a later provisioning run."""
    from datetime import timedelta

    from django.utils import timezone

    from subscriptions.models import Plan, Subscription

    existing = Subscription.all_objects.filter(
        tenant=tenant, status=Subscription.Status.ACTIVE
    ).first()
    if existing:
        return existing

    plan = Plan.objects.filter(code=DEFAULT_PLAN_CODE).first()
    if plan is None:
        # The catalogue is seeded by subscriptions.0002. During a partial
        # migrate it may not exist yet; the post_migrate backstop will catch up.
        return None

    today = timezone.now().date()
    return Subscription.all_objects.create(
        tenant=tenant,
        plan=plan,
        status=Subscription.Status.ACTIVE,
        started_on=today,
        trial_ends_on=today + timedelta(days=TRIAL_DAYS),
    )


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

    from .context import tenant_context

    # slugify() returns "" for Arabic names, so fall back rather than blank.
    fallback = slugify(name).upper()[:20] or "MAIN"
    with tenant_context(tenant):
        return Branch.all_objects.create(tenant=tenant, name=name, code=code or fallback)


def create_tenant_admin(tenant, email, password=None, username="admin", branch=None):
    """The tenant's first user. Without one, nobody can log in to it.

    Returns (user, password). A generated password is returned so the caller
    can show it once — it is not stored anywhere in readable form.
    """
    from django.contrib.auth import get_user_model

    from accounts.models import ClinicRole

    from .context import tenant_context

    User = get_user_model()

    if password is None:
        password = get_random_string(14, allowed_chars=PASSWORD_ALPHABET)

    with tenant_context(tenant):
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
