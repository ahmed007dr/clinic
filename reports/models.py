from django.db import models
from tenants.models import TenantOwnedModel

class ReportRecipient(TenantOwnedModel):
    email = models.EmailField(verbose_name="عنوان الإيميل")
    name = models.CharField(max_length=100, blank=True, null=True, verbose_name="الاسم")
    is_active = models.BooleanField(default=True, verbose_name="نشط")

    def __str__(self):
        return self.email

    class Meta(TenantOwnedModel.Meta):
        verbose_name = "مستلم التقرير"
        verbose_name_plural = "مستلمو التقرير"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "email"], name="uniq_reportrecipient_email_per_tenant")
        ]