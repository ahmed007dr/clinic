from django.apps import AppConfig


class MedicalConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "medical"
    verbose_name = "السجلات الطبية"

    def ready(self):
        # A booking sent in to the doctor opens its visit (medical/checkin.py).
        from . import checkin  # noqa: F401
