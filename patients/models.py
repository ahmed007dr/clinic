# patients/models.py
from django.db import models
from branches.models import Branch

class Patient(models.Model):    
    name = models.CharField(max_length=100)
    national_id = models.CharField(max_length=20, blank=True, null=True)
    gender = models.CharField(max_length=10, choices=[('male', 'ذكر'), ('female', 'أنثى')], blank=True, null=True)
    birth_date = models.DateField(blank=True, null=True)
    phone1 = models.CharField(max_length=20, blank=True, null=True)
    phone2 = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    marital_status = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    photo = models.ImageField(upload_to='patients/', blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True)  # حقل جديد

    def __str__(self):
        return self.name