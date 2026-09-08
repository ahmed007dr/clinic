from django.apps import AppConfig

class AuditConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "audit"

    def ready(self):
        import sys

        # Noise reduction only: skip auditing schema work when it is obvious
        # we are doing schema work. This is NOT what makes migrations safe —
        # it misses `manage.py test` (which migrates to build the test
        # database), programmatic call_command("migrate"), and pytest.
        # The actual protection is the savepoint in create_audit_log.
        if "migrate" in sys.argv or "makemigrations" in sys.argv:
            return
        import audit.signals
