"""Shared serializer behaviour.

Two things every clinic resource needs, in one place so no serializer has to
remember them.
"""

from rest_framework import serializers


class ClinicSerializer(serializers.ModelSerializer):
    """Base for tenant-owned records.

    **`tenant` is never a field.** Not read-only, not write-once — absent. A
    serializer that exposes it hands the client the one value that decides
    which clinic a row belongs to, and read-only is a weaker guarantee than
    not existing: it survives a `Meta.fields = "__all__"` on a later model and
    a nested writable serializer, and this does not. The tenant is stamped by
    `ClinicViewSet.perform_create` and nowhere else.

    Server-generated identifiers are read-only for the same reason in
    miniature: `serial_number` is allocated by `SerialCounter` under a lock,
    and letting a client supply one would collide with a real receipt.
    """

    #: Fields the server owns. Merged into `Meta.read_only_fields`.
    SERVER_OWNED = (
        "uuid",
        "serial_number",
        "created_at",
        "updated_at",
        "created_by",
        "tenant",
    )

    def get_fields(self):
        fields = super().get_fields()
        fields.pop("tenant", None)
        fields.pop("id", None)
        for name in self.SERVER_OWNED:
            if name in fields:
                fields[name].read_only = True
        return fields

    @property
    def request_user(self):
        request = self.context.get("request")
        return getattr(request, "user", None)


class DisplayField(serializers.CharField):
    """A human-readable label alongside a UUID.

    Tables show a patient's name, not their identifier, and making the client
    fetch every related record to render one column is what turns a list screen
    into fifty requests. Always read-only.
    """

    def __init__(self, source, **kwargs):
        kwargs.setdefault("read_only", True)
        super().__init__(source=source, **kwargs)


class ActiveChoicesMixin:
    """Refuse a stopped service or clinic for anything new (2026-09-11).

    What was already booked or done under it stays as it was: the check only
    fires when the value is being set or changed, never on an untouched
    record that happens to point at something since stopped.
    """

    def _still_active(self, name, value):
        if value is None or getattr(value, "is_active", True):
            return value
        current = getattr(self.instance, f"{name}_id", None) if self.instance is not None else None
        if current == value.pk:
            return value
        from rest_framework import serializers

        raise serializers.ValidationError(
            "هذه الخدمة موقوفة." if name == "service" else "هذا الفرع موقوف."
        )

    def validate_service(self, value):
        return self._still_active("service", value)

    def validate_branch(self, value):
        return self._still_active("branch", value)
