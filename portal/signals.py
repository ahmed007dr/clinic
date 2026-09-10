"""Portal side effects of changes made elsewhere."""

from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.utils import timezone

from patients.models import Patient


@receiver(pre_save, sender=Patient)
def end_portal_sessions_on_phone_change(sender, instance, raw=False, **kwargs):
    """A new phone number ends every portal session for that patient.

    The phone is the portal login. If the clinic changes it — because the old
    number was wrong, or lost, or belonged to someone else — whoever was signed
    in under the old one must not stay signed in.
    """
    if raw or not instance.pk:
        return
    from .models import PortalSession

    old = Patient.all_objects.filter(pk=instance.pk).values_list("phone1", flat=True).first()
    if old is not None and old != instance.phone1:
        PortalSession.all_objects.filter(
            account__patient_id=instance.pk, revoked_at__isnull=True
        ).update(revoked_at=timezone.now())
