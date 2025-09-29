from django.db import models
from django.utils import timezone

class Appointment(models.Model):
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
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)
    serial_number = models.CharField(max_length=20, unique=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.serial_number:
            date = self.scheduled_date.date()
            base_serial = f"{date.strftime('%Y%m%d')}-"
            existing_count = Appointment.objects.filter(
                scheduled_date__date=date,
                serial_number__startswith=base_serial
            ).count()
            serial = f"{base_serial}{existing_count + 1:03d}"
            while Appointment.objects.filter(serial_number=serial).exists():
                existing_count += 1
                serial = f"{base_serial}{existing_count + 1:03d}"
            self.serial_number = serial
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.serial_number} - {self.patient.name}"
