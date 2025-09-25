# appointments/models.py
from django.db import models
from patients.models import Patient
from employees.models import Employee, Specialization
from services.models import Service
from accounts.models import User
from branches.models import Branch

class AppointmentStatus(models.Model):
    name = models.CharField(max_length=50, unique=True)  # Scheduled, Cancelled, ...
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name


class Appointment(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    doctor = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True,
                               limit_choices_to={"employee_type__name": "Doctor"})
    specialization = models.ForeignKey(Specialization, on_delete=models.SET_NULL, null=True, blank=True)
    service = models.ForeignKey(Service, on_delete=models.SET_NULL, null=True, blank=True)
    scheduled_date = models.DateTimeField()
    status = models.ForeignKey(AppointmentStatus, on_delete=models.SET_NULL, null=True, blank=True)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)


