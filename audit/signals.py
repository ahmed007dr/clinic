from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ImproperlyConfigured
from django.db.utils import OperationalError, ProgrammingError
from .models import AuditLog
from .middleware import get_current_request

EXCLUDED_MODELS = {"AuditLog", "Session"}


def create_audit_log(user, action, instance, description=""):
    """Helper لإنشاء AuditLog"""
    try:
        model_name = ContentType.objects.get_for_model(instance).model
    except (OperationalError, ProgrammingError, ImproperlyConfigured):
        # قاعدة البيانات لسه ما خلصتش إعدادها (أثناء migrate/loaddata)
        return

    object_id = instance.pk
    request = get_current_request()
    ip = request.META.get("REMOTE_ADDR") if request else None
    agent = request.META.get("HTTP_USER_AGENT") if request else None

    try:
        AuditLog.objects.create(
            user=user if user and getattr(user, "is_authenticated", False) else None,
            action=action,
            model_name=model_name,
            object_id=str(object_id),
            description=description,
            ip_address=ip,
            user_agent=agent,
            created_at=timezone.now(),
        )
    except (OperationalError, ProgrammingError):
        # نفس الفكرة: لسه الجداول ما خلصتش
        return


@receiver(post_save)
def log_model_save(sender, instance, created, **kwargs):
    if sender.__name__ in EXCLUDED_MODELS:
        return

    request = get_current_request()
    user = getattr(request, "user", None) if request else None

    action = "create" if created else "update"
    description = f"{action.capitalize()} {sender.__name__}"

    create_audit_log(user, action, instance, description)


@receiver(post_delete)
def log_model_delete(sender, instance, **kwargs):
    if sender.__name__ in EXCLUDED_MODELS:
        return

    request = get_current_request()
    user = getattr(request, "user", None) if request else None

    create_audit_log(user, "delete", instance, f"Deleted {sender.__name__}")
            