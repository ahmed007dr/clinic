# accounts/apps.py
from django.apps import AppConfig
from django.db.models.signals import post_migrate

def ensure_default_roles(sender, **kwargs):
    from accounts.models import ClinicRole
    ClinicRole.objects.get_or_create(name="Admin", defaults={"description": "System administrator"})
    ClinicRole.objects.get_or_create(name="Reception", defaults={"description": "Reception staff"})

class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    def ready(self):
        post_migrate.connect(ensure_default_roles, sender=self)
