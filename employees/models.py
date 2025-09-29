from django.db import models
from branches.models import Branch
from django.utils import timezone

class EmployeeType(models.Model):
    name = models.CharField(max_length=50)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name

class Specialization(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name

class SalaryType(models.Model):
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name

class Employee(models.Model):
    name = models.CharField(max_length=100)
    employee_type = models.ForeignKey(EmployeeType, on_delete=models.SET_NULL, null=True, blank=True)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    national_id = models.CharField(max_length=20, unique=True)
    phone1 = models.CharField(max_length=20, blank=True)
    phone2 = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    hire_date = models.DateField(null=False, blank=False, default=timezone.now)
    salary_type = models.ForeignKey(SalaryType, on_delete=models.SET_NULL, null=True, blank=True)
    salary_value = models.DecimalField(max_digits=10, decimal_places=2)
    specializations = models.ManyToManyField(Specialization, blank=True)
    serial_number = models.CharField(max_length=20, unique=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.serial_number:
            date = self.hire_date
            base_serial = f"{date.strftime('%Y%m%d')}-"
            existing_count = Employee.objects.filter(
                hire_date=date,
                serial_number__startswith=base_serial
            ).count()
            serial = f"{base_serial}{existing_count + 1:03d}"
            while Employee.objects.filter(serial_number=serial).exists():
                existing_count += 1
                serial = f"{base_serial}{existing_count + 1:03d}"
            self.serial_number = serial
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.serial_number} - {self.name}"