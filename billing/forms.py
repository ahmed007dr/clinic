from django import forms
from .models import Payment, Expense, ExpenseCategory

class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ['appointment', 'patient', 'method', 'receipt_number', 'amount', 'branch', 'notes']
        widgets = {
            'appointment': forms.Select(attrs={'class': 'form-control js-example-basic-single'}),
            'patient': forms.Select(attrs={'class': 'form-control js-example-basic-single'}),
            'method': forms.Select(attrs={'class': 'form-control js-example-basic-single'}),
            'receipt_number': forms.TextInput(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control'}),
            'branch': forms.Select(attrs={'class': 'form-control js-example-basic-single'}),
            'notes': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
        }

class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ['branch', 'category', 'employee', 'amount', 'date', 'notes']
        widgets = {
            'branch': forms.Select(attrs={'class': 'form-control js-example-basic-single'}),
            'category': forms.Select(attrs={'class': 'form-control js-example-basic-single'}),
            'employee': forms.Select(attrs={'class': 'form-control js-example-basic-single'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control'}),
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
        }

class ExpenseCategoryForm(forms.ModelForm):
    class Meta:
        model = ExpenseCategory
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
        }