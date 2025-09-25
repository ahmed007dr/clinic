# notifications/models.py
from django.db import models
from django.conf import settings

class Notification(models.Model):
    NOTIFY_TYPE = (
        ("system", "System"),
        ("reminder", "Reminder"),
        ("warning", "Warning"),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    type = models.CharField(max_length=20, choices=NOTIFY_TYPE, default="system")
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} → {self.user}"
