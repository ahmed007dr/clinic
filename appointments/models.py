from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone
from tenants.models import SerialCounter, TenantOwnedModel

class Appointment(TenantOwnedModel):
    STATUS_CHOICES = [
        ("entered", "تم الدخول"),
        ("waiting", "الانتظار"),
        ("called", "تم الاتصال بالهاتف"),
        ("quick", "حجز سريع"),
    ]

    patient = models.ForeignKey('patients.Patient', on_delete=models.CASCADE)
    doctor = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={"employee_type__name": "Doctor"}
    )
    specialization = models.ForeignKey('employees.Specialization', on_delete=models.SET_NULL, null=True, blank=True)
    service = models.ForeignKey('services.Service', on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="waiting")
    branch = models.ForeignKey('branches.Branch', on_delete=models.SET_NULL, null=True, blank=True)
    scheduled_date = models.DateTimeField()
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    created_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)
    serial_number = models.CharField(max_length=20, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "serial_number"], name="uniq_appointment_serial_per_tenant")
        ]

    def save(self, *args, **kwargs):
        if not self.serial_number:
            self.serial_number = SerialCounter.next_serial(
                self.tenant_id, "appointment", self.scheduled_date.date()
            )
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.serial_number} - {self.patient.name}"
