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

    class Meta(TenantOwnedModel.Meta):
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

class EmailLog(TenantOwnedModel):
    """One email the system sent (or tried to) for a clinic, kept so the
    clinic's staff and the platform's support can see what went out, to whom,
    and exactly what it said (notifications/maillog.py).

    The body is what the recipient received — except for messages that carry a
    live credential (a sign-in code, a single-use link), where the credential
    is masked before it is stored. A log that kept them would let anyone who can
    read it sign in as the recipient.
    """

    class Status(models.TextChoices):
        SENT = "sent", "أُرسلت"
        FAILED = "failed", "فشلت"

    branch = models.ForeignKey("branches.Branch", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    kind = models.CharField(max_length=30, db_index=True)
    to_address = models.CharField(max_length=254, db_index=True)
    from_address = models.CharField(max_length=254, blank=True, default="")
    subject = models.CharField(max_length=300)
    body = models.TextField(blank=True, default="")
    is_html = models.BooleanField(default=False)
    #: The Django template the body was rendered from, when it was.
    template = models.CharField(max_length=120, blank=True, default="")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SENT)
    #: Why it failed — the exception's class name, never its text (which can
    #: echo a password or a server address).
    error = models.CharField(max_length=120, blank=True, default="")
    #: Set when this row is a re-send: the message it repeats (always the first
    #: send, never another re-send), so one message's whole history is one query.
    resent_from = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="resends")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["tenant", "-created_at"], name="emaillog_tenant_time")]

    def __str__(self):
        return f"{self.kind} → {self.to_address}"
