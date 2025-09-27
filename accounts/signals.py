from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

User = get_user_model()


@receiver(post_save, sender=User)
def set_default_role(sender, instance, created, **kwargs):
    if created and not instance.role:
        from accounts.models import ClinicRole
        default_role, _ = ClinicRole.objects.get_or_create(name="Reception")
        instance.role = default_role
        instance.save()
