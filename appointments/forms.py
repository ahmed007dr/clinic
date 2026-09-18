from django import forms
from .models import Appointment
from tenants.forms import TenantScopedFormMixin

class AppointmentForm(TenantScopedFormMixin, forms.ModelForm):
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


    def clean(self):
        """The old screens obey the same rule as the API: a patient goes in to
        the doctor only once the booking is paid in full (billing.collect)."""
        from billing.collect import PaymentRequired, check_can_enter, require_paid

        data = super().clean()
        if data.get("status") != "entered" or self.instance.status == "entered":
            return data
        try:
            if self.instance.pk:
                check_can_enter(self.instance, price=data.get("price"))
            else:
                require_paid(data.get("price") or 0)
        except PaymentRequired as required:
            self.add_error("status", str(required))
        return data


class SearchForm(forms.Form):
    query = forms.CharField(max_length=100, required=False, widget=forms.TextInput(attrs={'placeholder': 'ابحث باسم العميل أو الطبيب'}))
    