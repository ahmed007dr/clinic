from django.apps import AppConfig

class AuditConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "audit"

    def ready(self):
        import sys
        # ما تسجلش الـ signals أثناء migrate أو makemigrations
        if "migrate" in sys.argv or "makemigrations" in sys.argv:
            return
        import audit.signals
