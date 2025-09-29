from django.apps import AppConfig
from django.db.models.signals import post_migrate

def ensure_doctor_type(sender, **kwargs):
    from employees.models import EmployeeType
    EmployeeType.objects.get_or_create(name="Doctor", defaults={"description": "Medical Doctor"})

class EmployeesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "employees"

    def ready(self):
        post_migrate.connect(ensure_doctor_type, sender=self)
