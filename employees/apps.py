from django.apps import AppConfig
from django.db.models.signals import post_migrate

def ensure_doctor_type(sender, **kwargs):
    """EmployeeType is tenant-owned, so seed it per tenant.

    Appointment.doctor depends on this via limit_choices_to, so every tenant
    needs its own "Doctor" row. Moves into tenant provisioning at TENANT-008.
    """
    from employees.models import EmployeeType
    from tenants.models import Tenant

    for tenant in Tenant.objects.all():
        EmployeeType.objects.get_or_create(
            tenant=tenant, name="Doctor", defaults={"description": "Medical Doctor"}
        )

class EmployeesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "employees"

    def ready(self):
        post_migrate.connect(ensure_doctor_type, sender=self)
