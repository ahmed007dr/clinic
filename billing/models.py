# billing/models.py
from django.db import models
from patients.models import Patient
from appointments.models import Appointment
from branches.models import Branch
from employees.models import Employee  
from django.conf import settings



class PaymentMethod(models.Model):
    name = models.CharField(max_length=50, unique=True)  # Cash, Visa, Insurance, etc
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name


class Payment(models.Model):
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name="payments")
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    method = models.ForeignKey(PaymentMethod, on_delete=models.SET_NULL, null=True)
    receipt_number = models.CharField(max_length=50, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True)
    date = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Payment {self.receipt_number} - {self.amount} EGP"


class ExpenseCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name


class Expense(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="expenses")
    category = models.ForeignKey(ExpenseCategory, on_delete=models.SET_NULL, null=True, blank=True)

    employee = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name="expenses")

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.category.name if self.category else 'غير محدد'} - {self.amount}"
