from django.db.models.signals import post_save
from django.dispatch import receiver
from appointments.models import Appointment
from billing.models import Payment
from .models import Notification
from django.contrib.auth.models import User

@receiver(post_save, sender=Appointment)
def create_appointment_notification(sender, instance, created, **kwargs):
    if created:
        # إرسال إشعار إلى جميع المستخدمين في نفس الفرع
        users = User.objects.filter(branch=instance.branch)
        for user in users:
            Notification.objects.create(
                user=user,
                title=f"موعد جديد: {instance.id}",
                message=f"تم حجز موعد جديد للمريض {instance.patient.name} مع الطبيب {instance.doctor.name if instance.doctor else 'غير محدد'} في {instance.scheduled_date}",
                type='appointment'
            )

@receiver(post_save, sender=Payment)
def create_payment_notification(sender, instance, created, **kwargs):
    if created:
        # إرسال إشعار إلى جميع المستخدمين في نفس الفرع
        users = User.objects.filter(branch=instance.branch)
        for user in users:
            Notification.objects.create(
                user=user,
                title=f"دفعة جديدة: {instance.receipt_number}",
                message=f"تم تسجيل دفعة جديدة بقيمة {instance.amount} جنيه للمريض {instance.patient.name}",
                type='payment'
            )