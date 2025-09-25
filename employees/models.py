# employees/models.py
from django.db import models
from branches.models import Branch
class Specialization(models.Model):
    name = models.CharField(max_length=100, unique=True)  # Dermatology, Cardiology, etc
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name
# employees/models.py
class EmployeeType(models.Model):
    name = models.CharField(max_length=50, unique=True)  # Doctor, Nurse, Accountant...
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name


class Employee(models.Model):
    name = models.CharField(max_length=150)
    employee_type = models.ForeignKey(EmployeeType, on_delete=models.SET_NULL, null=True, blank=True)
    specializations = models.ManyToManyField("Specialization", blank=True)
    national_id = models.CharField(max_length=20, blank=True, null=True)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True)
    phone1 = models.CharField(max_length=15, blank=True, null=True)
    phone2 = models.CharField(max_length=15, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    hire_date = models.DateField(auto_now_add=True)
    salary_type = models.ForeignKey("SalaryType", on_delete=models.SET_NULL, null=True, blank=True)
    salary_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.name} - {self.employee_type}"
