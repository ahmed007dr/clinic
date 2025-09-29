from django.db.models.signals import post_save
from django.dispatch import receiver
from appointments.models import Appointment
from billing.models import Payment
from .models import Notification
from django.contrib.auth import get_user_model
User = get_user_model()

@receiver(post_save, sender=Appointment)
def create_appointment_notification(sender, instance, created, **kwargs):
    if created:
        users = User.objects.filter(branch=instance.branch)
        for user in users:
            notification = Notification(
                user=user,
                title=f"موعد جديد: {instance.serial_number}",
                message=f"تم حجز موعد جديد للمريض {instance.patient.name} مع الطبيب {instance.doctor.name if instance.doctor else 'غير محدد'} في {instance.scheduled_date}",
                type='appointment'
            )
            notification.save()

@receiver(post_save, sender=Payment)
def create_payment_notification(sender, instance, created, **kwargs):
    if created:
        users = User.objects.filter(branch=instance.branch)
        for user in users:
            notification = Notification(
                user=user,
                title=f"دفعة جديدة: {instance.receipt_number}",
                message=f"تم تسجيل دفعة جديدة بقيمة {instance.amount} جنيه للمريض {instance.patient.name}",
                type='payment'
            )
            notification.save()