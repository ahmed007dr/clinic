from django import forms
from django.forms import inlineformset_factory

from .models import (
    Allergy,
    Prescription,
    PrescriptionItem,
    TreatmentPlan,
    TreatmentSession,
    Visit,
)
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


class TreatmentPlanForm(TenantScopedFormMixin, forms.ModelForm):
    """TenantScopedFormMixin is not optional here: doctor, branch and service
    are all ModelChoiceFields, and their querysets would otherwise be built at
    import time with no tenant in context — leaving every dropdown empty."""

    class Meta:
        model = TreatmentPlan
        fields = [
            "title", "service", "doctor", "branch",
            "planned_sessions", "status", "start_date", "notes",
        ]
        widgets = {
            "title": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "مثال: علاج بالليزر"}
            ),
            "service": forms.Select(attrs={"class": "form-control js-example-basic-single"}),
            "doctor": forms.Select(attrs={"class": "form-control js-example-basic-single"}),
            "branch": forms.Select(attrs={"class": "form-control js-example-basic-single"}),
            "planned_sessions": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "status": forms.Select(attrs={"class": "form-control js-example-basic-single"}),
            "start_date": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"
            ),
            "notes": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        }


class TreatmentSessionForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = TreatmentSession
        fields = [
            "service", "doctor", "branch", "scheduled_date", "performed_at",
            "status", "quantity", "unit_price", "discount", "payment",
            "result", "notes",
        ]
        widgets = {
            "service": forms.Select(attrs={"class": "form-control js-example-basic-single"}),
            "doctor": forms.Select(attrs={"class": "form-control js-example-basic-single"}),
            "branch": forms.Select(attrs={"class": "form-control js-example-basic-single"}),
            "payment": forms.Select(attrs={"class": "form-control js-example-basic-single"}),
            "status": forms.Select(attrs={"class": "form-control js-example-basic-single"}),
            "scheduled_date": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "form-control"}, format="%Y-%m-%dT%H:%M"
            ),
            "performed_at": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "form-control"}, format="%Y-%m-%dT%H:%M"
            ),
            "quantity": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "unit_price": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "discount": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "result": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
            "notes": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("scheduled_date", "performed_at"):
            self.fields[name].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"]

    def clean(self):
        """The database refuses a discount larger than the line it discounts
        (`session_discount_within_total`). Checking it here too turns that into
        a field error the doctor can act on, instead of an IntegrityError."""
        cleaned = super().clean()
        quantity = cleaned.get("quantity")
        unit_price = cleaned.get("unit_price")
        discount = cleaned.get("discount")
        if quantity is not None and unit_price is not None and discount is not None:
            if discount > unit_price * quantity:
                self.add_error(
                    "discount", "الخصم لا يمكن أن يتجاوز إجمالي الجلسة"
                )
        return cleaned


class PrescriptionForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = Prescription
        fields = ["doctor", "issued_at", "notes"]
        widgets = {
            "doctor": forms.Select(attrs={"class": "form-control js-example-basic-single"}),
            "issued_at": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "form-control"}, format="%Y-%m-%dT%H:%M"
            ),
            "notes": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["issued_at"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"]


class PrescriptionItemForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = PrescriptionItem
        fields = ["medication", "dosage", "frequency", "duration", "instructions"]
        widgets = {
            "medication": forms.TextInput(attrs={"class": "form-control", "placeholder": "اسم الدواء"}),
            "dosage": forms.TextInput(attrs={"class": "form-control", "placeholder": "مثال: 500 مجم"}),
            "frequency": forms.TextInput(attrs={"class": "form-control", "placeholder": "مثال: مرتين يومياً"}),
            "duration": forms.TextInput(attrs={"class": "form-control", "placeholder": "مثال: 7 أيام"}),
            "instructions": forms.TextInput(attrs={"class": "form-control", "placeholder": "مثال: بعد الأكل"}),
        }


# A prescription is meaningless without at least one medication, so validate_min
# rather than letting an empty document be issued.
PrescriptionItemFormSet = inlineformset_factory(
    Prescription,
    PrescriptionItem,
    form=PrescriptionItemForm,
    extra=3,
    min_num=1,
    validate_min=True,
    can_delete=True,
)
