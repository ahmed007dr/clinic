from django.db import models, transaction
from django.conf import settings
from django.utils import timezone
from tenants.models import TenantOwnedModel

class Notification(TenantOwnedModel):
    NOTIFY_TYPE = (
        ("system", "نظام"),
        ("reminder", "تذكير"),
        ("warning", "تحذير"),
        ("appointment", "موعد"),
        ("payment", "دفع"),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    type = models.CharField(max_length=20, choices=NOTIFY_TYPE, default="system")
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    serial_number = models.CharField(max_length=20, unique=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.serial_number:
            with transaction.atomic():
                date = self.created_at.date() if self.created_at else timezone.now().date()
                base_serial = f"{date.strftime('%Y%m%d')}-"
                existing_count = Notification.objects.select_for_update().filter(
                    created_at__date=date,
                    serial_number__startswith=base_serial
                ).count()
                serial = f"{base_serial}{existing_count + 1:03d}"
                while Notification.objects.filter(serial_number=serial).exists():
                    existing_count += 1
                    serial = f"{base_serial}{existing_count + 1:03d}"
                self.serial_number = serial
                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.serial_number} - {self.title}"