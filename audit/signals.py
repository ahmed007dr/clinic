from django.db import transaction
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ImproperlyConfigured
from django.db.utils import DatabaseError, OperationalError, ProgrammingError, IntegrityError
from .models import AuditLog
from .middleware import get_current_request

# ContentType/Migration are Django's own bookkeeping models — auditing them
# is meaningless noise, and saving them fires during migrate/loaddata before
# their own schema is fully settled (e.g. contenttypes.0001 creates
# django_content_type with a NOT NULL "name" column that 0002 later drops;
# a ContentType lookup from this signal in between the two would otherwise
# raise IntegrityError and abort the migration).
EXCLUDED_MODELS = {"AuditLog", "Session", "ContentType", "Migration"}


def create_audit_log(user, action, instance, description=""):
    """Write one audit row, and never break the caller's transaction.

    Every risky statement runs inside its own savepoint. On PostgreSQL a failed
    statement poisons the entire transaction — every later statement raises
    "current transaction is aborted" — so catching the error is not enough on
    its own: without a savepoint to roll back to, swallowing it leaves the
    connection unusable and the *caller* dies instead.

    That is not hypothetical. It made `manage.py test` fail outright on
    PostgreSQL while passing on SQLite, which tolerates the same mistake.
    """
    try:
        with transaction.atomic():
            model_name = ContentType.objects.get_for_model(instance).model
    except (OperationalError, ProgrammingError, ImproperlyConfigured, IntegrityError):
        # Schema not settled yet — during migrate or loaddata.
        return

    object_id = instance.pk
    request = get_current_request()
    ip = request.META.get("REMOTE_ADDR") if request else None
    agent = request.META.get("HTTP_USER_AGENT") if request else None

    try:
        with transaction.atomic():
            AuditLog.objects.create(
                # tenant_id, not tenant. During a data migration the instance is
                # a *historical* model built by apps.get_model, so its `.tenant`
                # is a historical Tenant that Django refuses to assign to a
                # relation declared against the real one — the save blows up and
                # takes the migration with it. The id is just an integer and
                # works for both, and it saves fetching the related row too.
                # Same lesson as BUG-001: auditing must never be able to break
                # the operation it is observing.
                tenant_id=getattr(instance, "tenant_id", None),
                user=user if user and getattr(user, "is_authenticated", False) else None,
                action=action,
                model_name=model_name,
                object_id=str(object_id),
                description=description,
                ip_address=ip,
                user_agent=agent,
                created_at=timezone.now(),
            )
    except DatabaseError:
        # Auditing must never be the reason a real operation fails.
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
            