from django.db import models
from django.conf import settings
from django.utils import timezone
from tenants.models import SerialCounter, TenantOwnedModel

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
    serial_number = models.CharField(max_length=20, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "serial_number"], name="uniq_notification_serial_per_tenant")
        ]

    def save(self, *args, **kwargs):
        if not self.serial_number:
            date = self.created_at.date() if self.created_at else timezone.now().date()
            self.serial_number = SerialCounter.next_serial(self.tenant_id, "notification", date)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.serial_number} - {self.title}"