from django.db import models
from django.core.validators import MinValueValidator
from branches.models import Branch
from django.utils import timezone
from tenants.models import SerialCounter, TenantOwnedModel

class EmployeeType(TenantOwnedModel):
    name = models.CharField(max_length=50)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name

class Specialization(TenantOwnedModel):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name

class SalaryType(TenantOwnedModel):
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name

class Employee(TenantOwnedModel):
    name = models.CharField(max_length=100)
    employee_type = models.ForeignKey(EmployeeType, on_delete=models.SET_NULL, null=True, blank=True)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    national_id = models.CharField(max_length=20)
    # 32 — see Branch.phone for why 20 was too narrow.
    phone1 = models.CharField(max_length=32, blank=True)
    phone2 = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    hire_date = models.DateField(null=False, blank=False, default=timezone.now)
    salary_type = models.ForeignKey(SalaryType, on_delete=models.SET_NULL, null=True, blank=True)
    salary_value = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    specializations = models.ManyToManyField(Specialization, blank=True)
    serial_number = models.CharField(max_length=20, blank=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "serial_number"], name="uniq_employee_serial_per_tenant"),
            models.UniqueConstraint(fields=["tenant", "national_id"], name="uniq_employee_national_id_per_tenant"),
        ]

    def save(self, *args, **kwargs):
        if not self.serial_number:
            self.serial_number = SerialCounter.next_serial(self.tenant_id, "employee", self.hire_date)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.serial_number} - {self.name}"