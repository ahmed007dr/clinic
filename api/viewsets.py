"""The base every clinic resource is built on.

One class carries the parts that must not be re-decided per resource: how a
record is addressed, which rows the caller can reach, and which tenant a new
record is stamped with. A viewset that subclasses this and adds nothing is
already correctly scoped; the failure mode of forgetting a line is a resource
that returns too little, never one that returns too much.
"""

from rest_framework import viewsets
from rest_framework.exceptions import ValidationError

from tenants.context import get_current_tenant

from .permissions import IsClinicMember, scope_queryset_to_user


class ClinicViewSet(viewsets.ModelViewSet):
    """A tenant-owned resource, addressed by UUID and scoped to the caller."""

    permission_classes = [IsClinicMember]

    # Sequential primary keys stay internal (SEC-011): `/api/patients/1247/`
    # would disclose roughly how many patients a clinic has and make walking
    # every record trivial for anyone already inside the tenant.
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"
    lookup_value_regex = "[0-9a-fA-F-]{36}"

    #: Set to a lookup path to hold non-admins to their own branch. `None`
    #: means the resource is legitimately clinic-wide (services, categories).
    branch_field = "branch"

    #: Model attribute to stamp with the acting user on create, when the model
    #: has one. Kept explicit rather than guessed from the field list.
    created_by_field = None

    #: A key from `subscriptions.entitlements.LIMITS` that caps how many of
    #: these a clinic may create. Mirrors the server-rendered views exactly:
    #: an API that skipped the check would be a second door around the plan.
    plan_limit = None

    def get_queryset(self):
        """Resolved per request, never cached on the class.

        `Model.objects` reads the tenant from a contextvar, so a queryset built
        at import time is frozen empty — the same trap `api/relations.py`
        documents. Building it here means it is evaluated while a request, and
        therefore a tenant, is in scope.
        """
        queryset = self.queryset.model._default_manager.all()
        queryset = self.filter_tenant_queryset(queryset)
        if self.branch_field:
            queryset = scope_queryset_to_user(
                queryset, self.request.user, self.branch_field
            )
        ordering = getattr(self, "ordering", None)
        return queryset.order_by(*ordering) if ordering else queryset

    def filter_tenant_queryset(self, queryset):
        """Hook for `select_related` and resource-specific narrowing."""
        return queryset

    def perform_create(self, serializer):
        """Stamp the tenant server-side. It is never accepted from input.

        Taking the tenant from the payload — even to validate it — would make
        switching clinics a matter of editing one field, so the serializers do
        not declare it at all and this is the only place it is set.
        """
        tenant = get_current_tenant()
        if tenant is None:
            # Unreachable through the middleware for an authenticated clinic
            # user, and a loud failure rather than a row with no owner if the
            # stack is ever reordered.
            raise ValidationError("تعذّر تحديد العيادة الحالية.")
        if self.plan_limit:
            self.enforce_plan_limit(tenant)
        extra = {"tenant": tenant}
        if self.created_by_field:
            extra[self.created_by_field] = self.request.user
        serializer.save(**extra)

    def plan_limit_count(self):
        """How many already count against the plan. Overridable, because not
        every row is a counted one (a pending self-registration is not)."""
        return self.queryset.model._default_manager.count()

    def enforce_plan_limit(self, tenant):
        """Refuse a create that would exceed the clinic's plan.

        Counted over the whole tenant, not the caller's branch: the plan caps
        the clinic, and a receptionist's branch-scoped view of the table would
        undercount and let them past the limit.
        """
        from rest_framework.exceptions import PermissionDenied

        from subscriptions.entitlements import LimitReached, check_limit

        model = self.queryset.model
        try:
            check_limit(tenant, self.plan_limit, self.plan_limit_count())
        except LimitReached as reached:
            raise PermissionDenied(
                f"باقتك الحالية تسمح بـ {reached.allowed} فقط. "
                "تواصل معنا لترقية الباقة."
            )

    def perform_update(self, serializer):
        # Tenant is immutable: a record does not move between clinics, and the
        # serializer has no field for it, but saying so here makes that a
        # property of the base class rather than of every serializer.
        serializer.save()


class ReadOnlyClinicViewSet(ClinicViewSet):
    """Same scoping, no writes. For resources the API only ever reports on."""

    http_method_names = ["get", "head", "options"]
