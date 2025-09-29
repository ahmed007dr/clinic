# patients/models.py
from django.db import models
from branches.models import Branch
from django.utils import timezone

class Patient(models.Model):   


    GENDER_CHOICES = (
        ('male', 'ذكر'),
        ('female', 'أنثى'),
    )
    MARITAL_STATUS_CHOICES = (
        ('single', 'أعزب'),
        ('married', 'متزوج'),
    )


    name = models.CharField(max_length=100)
    national_id = models.CharField(max_length=20, blank=True, null=True)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, default='female')
    marital_status = models.CharField(max_length=20, choices=MARITAL_STATUS_CHOICES, default='single')
    birth_date = models.DateField(blank=True, null=True)
    phone1 = models.CharField(max_length=20, blank=True, null=True)
    phone2 = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    photo = models.ImageField(upload_to='patients/', blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True) 
    serial_number = models.CharField(max_length=20, unique=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)  # تاريخ الإنشاء أول مرة
    updated_at = models.DateTimeField(auto_now=True)      # آخر تعديل

    def save(self, *args, **kwargs):
        if not self.serial_number:
            date = timezone.now().date()  
            base_serial = f"{date.strftime('%Y%m%d')}-"
            existing_count = Patient.objects.filter(
                created_at__date=date,
                serial_number__startswith=base_serial
            ).count()
            serial = f"{base_serial}{existing_count + 1:03d}"
            while Patient.objects.filter(serial_number=serial).exists():
                existing_count += 1
                serial = f"{base_serial}{existing_count + 1:03d}"
            self.serial_number = serial
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.serial_number} - {self.name}"
        