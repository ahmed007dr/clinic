"""Relating one tenant-owned record to another, without freezing the tenant.

This module exists because of a single sharp edge that would otherwise be
invisible until a clinic reported that nothing could be saved.

The obvious way to declare a foreign key in a serializer is:

    patient = serializers.SlugRelatedField(
        slug_field="uuid", queryset=Patient.objects.all()
    )

`Patient.objects` is `TenantManager`, which reads the tenant from a contextvar
and **fails closed** — no tenant in context means `.none()`. That `.all()` runs
once, at import time, while Django is still loading modules and no request is in
flight. So the field is born holding an empty queryset and keeps it for the life
of the process: every write is rejected with "object does not exist", for every
clinic, forever.

The fix is to resolve the queryset per request instead of per process. DRF calls
`get_queryset()` on each validation, so overriding it is enough.

Doing it this way also buys the authorization for free. Because the queryset is
`Model.objects` evaluated inside the request, it is already filtered to the
caller's tenant — so a client that posts another clinic's patient UUID gets an
ordinary validation error, not a cross-tenant write. The check is not something
each serializer has to remember; it is the only thing this field can do.
"""

from rest_framework import serializers

from .permissions import scope_queryset_to_user


class TenantScopedRelatedField(serializers.SlugRelatedField):
    """A foreign key addressed by UUID and resolved inside the request.

    `model` replaces `queryset`: passing a queryset is what causes the freeze
    described above, so this field refuses one and builds its own.

    `branch_field` additionally holds the choices to the caller's own branch,
    for the same reason list endpoints do — a receptionist who cannot see a
    patient must not be able to attach that patient to a new appointment by
    UUID. Leave it None where a record is legitimately clinic-wide, such as a
    service or an expense category.
    """

    def __init__(self, model, branch_field=None, **kwargs):
        self.model = model
        self.branch_field = branch_field
        kwargs.setdefault("slug_field", "uuid")
        # DRF requires one or the other; ours is computed, so declare read-only
        # intent away and supply the queryset through get_queryset() below.
        kwargs.pop("queryset", None)
        super().__init__(queryset=model._default_manager.none(), **kwargs)

    def get_queryset(self):
        # Fresh every call: this is the whole point of the class.
        queryset = self.model._default_manager.all()
        request = self.context.get("request")
        if request is not None and self.branch_field:
            queryset = scope_queryset_to_user(
                queryset, request.user, self.branch_field
            )
        return queryset

    def to_internal_value(self, data):
        """Report a missing target as a plain validation error.

        `SlugRelatedField` raises `does_not_exist` already; what matters here is
        that a UUID belonging to another clinic produces exactly the same
        message as one that was never issued. Distinguishing them would confirm
        the existence of another clinic's records to anyone willing to guess.
        """
        if data in ("", None):
            self.fail("null")
        try:
            return super().to_internal_value(data)
        except serializers.ValidationError:
            raise serializers.ValidationError(
                "لا يوجد سجل بهذا المعرّف."
            )
