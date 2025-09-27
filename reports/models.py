from django.db import models

class ReportRecipient(models.Model):
    email = models.EmailField(unique=True, verbose_name="عنوان الإيميل")
    name = models.CharField(max_length=100, blank=True, null=True, verbose_name="الاسم")
    is_active = models.BooleanField(default=True, verbose_name="نشط")

    def __str__(self):
        return self.email

    class Meta:
        verbose_name = "مستلم التقرير"
        verbose_name_plural = "مستلمو التقرير"