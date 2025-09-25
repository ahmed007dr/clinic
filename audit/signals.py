from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from .models import AuditLog
from .middleware import get_current_request


def create_audit_log(user, action, instance, description=""):
    """Helper لإنشاء AuditLog"""
    model_name = ContentType.objects.get_for_model(instance).model
    object_id = instance.pk

    request = get_current_request()
    ip = request.META.get("REMOTE_ADDR") if request else None
    agent = request.META.get("HTTP_USER_AGENT") if request else None

    AuditLog.objects.create(
        user=user if user and user.is_authenticated else None,
        action=action,
        model_name=model_name,
        object_id=str(object_id),
        description=description,
        ip_address=ip,
        user_agent=agent,
        created_at=timezone.now(),
    )


@receiver(post_save)
def log_model_save(sender, instance, created, **kwargs):
    """يسجل create/update لأي موديل"""
    # استثني AuditLog نفسه علشان ما يعملش recursion
    if sender == AuditLog:
        return

    request = get_current_request()
    user = getattr(request, "user", None)

    if created:
        create_audit_log(user, "create", instance, f"Created {sender.__name__}")
    else:
        create_audit_log(user, "update", instance, f"Updated {sender.__name__}")


@receiver(post_delete)
def log_model_delete(sender, instance, **kwargs):
    """يسجل delete لأي موديل"""
    if sender == AuditLog:
        return

    request = get_current_request()
    user = getattr(request, "user", None)

    create_audit_log(user, "delete", instance, f"Deleted {sender.__name__}")
