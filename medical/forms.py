from django import forms

from .models import Allergy, Visit
from tenants.forms import TenantScopedFormMixin


class VisitForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = Visit
        fields = [
            "doctor", "branch", "visit_date", "chief_complaint",
            "examination", "diagnosis", "treatment_plan", "follow_up_date",
        ]
        widgets = {
            "doctor": forms.Select(attrs={"class": "form-control js-example-basic-single"}),
            "branch": forms.Select(attrs={"class": "form-control js-example-basic-single"}),
            "visit_date": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "form-control"}, format="%Y-%m-%dT%H:%M"
            ),
            "chief_complaint": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
            "examination": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
            "diagnosis": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
            "treatment_plan": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
            "follow_up_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["visit_date"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"]


class AllergyForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = Allergy
        fields = ["substance", "reaction", "severity", "notes"]
        widgets = {
            "substance": forms.TextInput(attrs={"class": "form-control"}),
            "reaction": forms.TextInput(attrs={"class": "form-control"}),
            "severity": forms.Select(attrs={"class": "form-control js-example-basic-single"}),
            "notes": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        }
