from django import forms
from .models import Patient

class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient
        fields = ['name', 'phone1', 'phone2', 'birth_date', 'national_id', 'gender', 'marital_status', 'email', 'address', 'photo', 'notes']
        widgets = {
            'birth_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
            'gender': forms.Select(attrs={'class': 'form-control js-example-basic-single'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone1': forms.TextInput(attrs={'class': 'form-control'}),
            'phone2': forms.TextInput(attrs={'class': 'form-control'}),
            'national_id': forms.TextInput(attrs={'class': 'form-control'}),
            'marital_status': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
            'photo': forms.FileInput(attrs={'class': 'file-upload-default'}),
        }