# patients/models.py
from django.db import models

class Patient(models.Model):
    name = models.CharField(max_length=150)
    phone1 = models.CharField(max_length=15, blank=True, null=True)
    phone2 = models.CharField(max_length=15, blank=True, null=True)
    birth_date = models.DateField(blank=True, null=True)
    national_id = models.CharField(max_length=20, blank=True, null=True)
    gender = models.CharField(max_length=10, choices=[("male", "Male"), ("female", "Female")])
    marital_status = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    photo = models.ImageField(upload_to="patients/", blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name
