# accounts/models.py
from django.db import models
from django.contrib.auth.models import AbstractUser

class ClinicRole(models.Model):
    name = models.CharField(max_length=50, unique=True)  # Doctor, Reception, Accountant, etc
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name


class User(AbstractUser):
    clinic_code = models.CharField(max_length=20)  # كود العيادة
    role = models.ForeignKey(ClinicRole, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.username} ({self.role})"
