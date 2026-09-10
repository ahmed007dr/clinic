from django.conf import settings
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


class Attendance(TenantOwnedModel):
    """One employee's day: present, late, absent or on leave.

    One row per employee per day. `branch` is the clinic where it was recorded
    — it decides who may see it, and lets the group compare clinics.
    """

    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        LATE = "late", "Late"
        ABSENT = "absent", "Absent"
        LEAVE = "leave", "On leave"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="attendance")
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True)
    date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices)
    check_in = models.TimeField(null=True, blank=True)
    check_out = models.TimeField(null=True, blank=True)
    minutes_late = models.PositiveIntegerField(null=True, blank=True)
    notes = models.CharField(max_length=200, blank=True, default="")
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "employee", "date"], name="uniq_attendance_per_day")
        ]
        indexes = [models.Index(fields=["tenant", "branch", "date"], name="attendance_branch_date_idx")]

    def __str__(self):
        return f"{self.employee} {self.date} {self.status}"
