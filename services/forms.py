from django import forms
from .models import Service

class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = ['name', 'description', 'specialization', 'base_price']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
            'specialization': forms.Select(attrs={'class': 'form-control js-example-basic-single'}),
            'base_price': forms.NumberInput(attrs={'class': 'form-control'}),
        }