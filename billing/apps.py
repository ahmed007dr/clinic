from django.apps import AppConfig


class BillingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'billing'

    def ready(self):
        # Doctor shares accrue from payments (billing/commissions.py).
        from . import commissions  # noqa: F401
