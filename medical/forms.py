from pathlib import PurePath

from django import forms
from django.forms import inlineformset_factory

from .models import (
    Allergy,
    LabResult,
    MedicalAttachment,
    Prescription,
    PrescriptionItem,
    Procedure,
    TreatmentPlan,
    TreatmentSession,
    Visit,
)
from tenants.forms import TenantScopedFormMixin

from .attachments import checksum, validate_attachment


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


class MedicalAttachmentForm(TenantScopedFormMixin, forms.ModelForm):
    """Validation happens in `clean_file`, not on the model.

    The checks in medical/attachments.py need the *uploaded* object — its size,
    and its leading bytes — which only exists during form processing. By the
    time a model field has a value it may already be a stored file.

    The derived columns (content type, size, checksum, original name) are filled
    in here for the same reason: this is the only place the upload is still in
    hand. `clean_file` stashes what it detected so `save` does not have to read
    the file a second time.
    """

    class Meta:
        model = MedicalAttachment
        fields = ["title", "category", "file", "visit", "lab_result", "branch", "notes"]
        widgets = {
            "title": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "مثال: تقرير أشعة الصدر"}
            ),
            "category": forms.Select(attrs={"class": "form-control js-example-basic-single"}),
            "file": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "visit": forms.Select(attrs={"class": "form-control js-example-basic-single"}),
            "lab_result": forms.Select(attrs={"class": "form-control js-example-basic-single"}),
            "branch": forms.Select(attrs={"class": "form-control js-example-basic-single"}),
            "notes": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        }

    def clean_file(self):
        uploaded = self.cleaned_data.get("file")
        if not uploaded:
            return uploaded
        # An already-stored file on an edit has no fresh upload to inspect.
        if not hasattr(uploaded, "size") or not hasattr(uploaded, "read"):
            return uploaded

        extension, content_type = validate_attachment(uploaded)
        self._detected = {
            "content_type": content_type,
            "size_bytes": uploaded.size,
            "checksum": checksum(uploaded),
            # Only the base name is kept: the browser may send a path, and a
            # stored value containing separators is a trap for anything that
            # later joins it to a directory.
            "original_filename": PurePath(uploaded.name or "").name[:255],
        }
        return uploaded

    def save(self, commit=True):
        attachment = super().save(commit=False)
        for field, value in getattr(self, "_detected", {}).items():
            setattr(attachment, field, value)
        if commit:
            attachment.save()
        return attachment


class LabResultForm(TenantScopedFormMixin, forms.ModelForm):
    """`flag` is a field the clinician sets, not something derived from
    `value` and `reference_range` — see the model docstring for why inferring
    it would be a safety signal that is wrong some of the time.

    `acknowledged_by`/`acknowledged_at` are deliberately absent: acknowledgement
    is its own action with its own endpoint, so it cannot happen as a side
    effect of editing something else.
    """

    class Meta:
        model = LabResult
        fields = [
            "test_name", "specimen", "lab_name", "ordered_by", "branch", "visit",
            "status", "ordered_at", "resulted_at",
            "value", "unit", "reference_range", "flag", "notes",
        ]
        widgets = {
            "test_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "مثال: صورة دم كاملة"}
            ),
            "specimen": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "مثال: دم وريدي"}
            ),
            "lab_name": forms.TextInput(attrs={"class": "form-control"}),
            "ordered_by": forms.Select(attrs={"class": "form-control js-example-basic-single"}),
            "branch": forms.Select(attrs={"class": "form-control js-example-basic-single"}),
            "visit": forms.Select(attrs={"class": "form-control js-example-basic-single"}),
            "status": forms.Select(attrs={"class": "form-control js-example-basic-single"}),
            "flag": forms.Select(attrs={"class": "form-control js-example-basic-single"}),
            "ordered_at": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "form-control"},
                format="%Y-%m-%dT%H:%M",
            ),
            "resulted_at": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "form-control"},
                format="%Y-%m-%dT%H:%M",
            ),
            "value": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "مثال: 7.2 أو إيجابي"}
            ),
            "unit": forms.TextInput(attrs={"class": "form-control", "placeholder": "مثال: mg/dL"}),
            "reference_range": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "مثال: 4.0 - 5.6"}
            ),
            "notes": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("ordered_at", "resulted_at"):
            self.fields[name].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"]

    def clean(self):
        """A result cannot be reported as arrived with nothing in it. Without
        this, a row reads as `صدرت النتيجة` while the value is blank, which
        looks like a normal result rather than a missing one."""
        cleaned = super().clean()
        if cleaned.get("status") == LabResult.Status.RESULTED and not cleaned.get("value"):
            self.add_error("value", "أدخل النتيجة قبل تحديد الحالة كـ«صدرت النتيجة»")
        return cleaned


class ProcedureForm(TenantScopedFormMixin, forms.ModelForm):
    class Meta:
        model = Procedure
        fields = [
            "name", "service", "doctor", "branch", "performed_at", "status",
            "body_site", "quantity", "unit_price", "discount", "payment",
            "findings", "outcome", "complications", "notes",
        ]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "مثال: استئصال شامة"}
            ),
            "service": forms.Select(attrs={"class": "form-control js-example-basic-single"}),
            "doctor": forms.Select(attrs={"class": "form-control js-example-basic-single"}),
            "branch": forms.Select(attrs={"class": "form-control js-example-basic-single"}),
            "payment": forms.Select(attrs={"class": "form-control js-example-basic-single"}),
            "status": forms.Select(attrs={"class": "form-control js-example-basic-single"}),
            "performed_at": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "form-control"},
                format="%Y-%m-%dT%H:%M",
            ),
            "body_site": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "مثال: الساعد الأيمن"}
            ),
            "quantity": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "unit_price": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "discount": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "findings": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
            "outcome": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
            "complications": forms.Textarea(
                attrs={"rows": 3, "class": "form-control",
                       "placeholder": "اتركه فارغاً إذا لم تحدث مضاعفات"}
            ),
            "notes": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["performed_at"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"]

    def clean(self):
        """Mirrors `procedure_discount_within_total`, so an over-discount comes
        back as a field error the doctor can act on rather than an
        IntegrityError. Same rule and same reasoning as TreatmentSessionForm."""
        cleaned = super().clean()
        quantity = cleaned.get("quantity")
        unit_price = cleaned.get("unit_price")
        discount = cleaned.get("discount")
        if quantity is not None and unit_price is not None and discount is not None:
            if discount > unit_price * quantity:
                self.add_error("discount", "الخصم لا يمكن أن يتجاوز إجمالي الإجراء")
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
