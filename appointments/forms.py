from django import forms
from .models import Appointment

class AppointmentForm(forms.ModelForm):
    class Meta:
        model = Appointment
        fields = ['patient', 'doctor', 'service', 'scheduled_date', 'status', 'branch', 'price', 'notes']
        widgets = {
            'patient': forms.Select(attrs={'class': 'form-control js-example-basic-single'}),
            'doctor': forms.Select(attrs={'class': 'form-control js-example-basic-single'}),
            'service': forms.Select(attrs={'class': 'form-control js-example-basic-single'}),
            'status': forms.Select(attrs={'class': 'form-control js-example-basic-single'}),
            'branch': forms.Select(attrs={'class': 'form-control js-example-basic-single'}),
            'scheduled_date': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'price': forms.NumberInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
        }


class SearchForm(forms.Form):
    query = forms.CharField(max_length=100, required=False, widget=forms.TextInput(attrs={'placeholder': 'ابحث باسم العميل أو الطبيب'}))
    