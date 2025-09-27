from django import forms
from .models import Employee, EmployeeType, Specialization

class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = ['name', 'employee_type', 'specializations', 'national_id', 'branch', 'phone1', 'phone2', 'email', 'salary_type', 'salary_value']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'employee_type': forms.Select(attrs={'class': 'form-control js-example-basic-single'}),
            'specializations': forms.SelectMultiple(attrs={'class': 'form-control js-example-basic-multiple'}),
            'national_id': forms.TextInput(attrs={'class': 'form-control'}),
            'branch': forms.Select(attrs={'class': 'form-control js-example-basic-single'}),
            'phone1': forms.TextInput(attrs={'class': 'form-control'}),
            'phone2': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'salary_type': forms.Select(attrs={'class': 'form-control js-example-basic-single'}),
            'salary_value': forms.NumberInput(attrs={'class': 'form-control'}),
        }

class EmployeeTypeForm(forms.ModelForm):
    class Meta:
        model = EmployeeType
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
        }

class SpecializationForm(forms.ModelForm):
    class Meta:
        model = Specialization
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
        }