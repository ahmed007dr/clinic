# billing/models.py
from django.db import models
from django.core.validators import MinValueValidator
from patients.models import Patient
from appointments.models import Appointment
from branches.models import Branch
from employees.models import Employee  
from django.conf import settings
from tenants.models import TenantOwnedModel



class PaymentMethod(TenantOwnedModel):
    name = models.CharField(max_length=50)  # Cash, Visa, Insurance, etc
    description = models.TextField(blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="uniq_paymentmethod_name_per_tenant")
        ]

    def __str__(self):
        return self.name


class Payment(TenantOwnedModel):
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name="payments")
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    method = models.ForeignKey(PaymentMethod, on_delete=models.SET_NULL, null=True)
    receipt_number = models.CharField(max_length=50)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True)
    date = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "receipt_number"], name="uniq_payment_receipt_per_tenant")
        ]

    def __str__(self):
        return f"Payment {self.receipt_number} - {self.amount} EGP"


class ExpenseCategory(TenantOwnedModel):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="uniq_expensecategory_name_per_tenant")
        ]

    def __str__(self):
        return self.name


class Expense(TenantOwnedModel):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="expenses")
    category = models.ForeignKey(ExpenseCategory, on_delete=models.SET_NULL, null=True, blank=True)

    employee = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name="expenses")

    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    date = models.DateField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.category.name if self.category else 'غير محدد'} - {self.amount}"
