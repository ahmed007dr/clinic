from django.core.exceptions import FieldDoesNotExist
from django.forms.models import ModelChoiceField, ModelMultipleChoiceField


class TenantScopedFormMixin:
    """Rebuild relation querysets per form instance.

    Django builds a ModelChoiceField's queryset when the form *class* is
    imported — long before any request exists. The tenant-scoped manager
    therefore resolves with no tenant in context, fails closed, and bakes
    `.none()` into the field permanently. Every dropdown on every form ends up
    empty, and the form then rejects any choice submitted to it.

    Rebinding in __init__ evaluates the queryset while the request's tenant is
    in context. The queryset is reconstructed the same way Django's
    ForeignKey.formfield() does, so limit_choices_to (for example
    Appointment.doctor restricting to the Doctor employee type) is preserved.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        model = getattr(getattr(self, "_meta", None), "model", None)
        if model is None:
            return

        for name, field in self.fields.items():
            if not isinstance(field, (ModelChoiceField, ModelMultipleChoiceField)):
                continue
            try:
                model_field = model._meta.get_field(name)
            except FieldDoesNotExist:
                continue  # a plain form field that happens to hold a queryset
            remote = getattr(model_field, "remote_field", None)
            if remote is None:
                continue

            queryset = remote.model._default_manager.all()
            limit = model_field.get_limit_choices_to()
            if limit:
                queryset = queryset.complex_filter(limit)
            field.queryset = queryset
