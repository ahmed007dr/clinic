"""Everything a new tenant needs before it can be used.

Single source of truth for tenant setup: the post_migrate hook calls it for
existing tenants, the demo seeder calls it, and tenant onboarding (TENANT-008)
will call the same function rather than reinventing the list.
"""

from django.utils.text import slugify

DEFAULT_ROLES = [
    ("Admin", "System administrator"),
    ("Reception", "Reception staff"),
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
