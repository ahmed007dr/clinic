"""Staff accounts and clinic roles — Admin only."""

from django.contrib.auth import get_user_model
from rest_framework.filters import OrderingFilter, SearchFilter

from accounts.models import ClinicRole
from api.permissions import IsClinicAdmin, ReadOnlyForNonAdmin
from api.serializers.accounts import ClinicRoleSerializer, StaffUserSerializer
from api.viewsets import ClinicViewSet
from tenants.context import get_current_tenant

User = get_user_model()


class ClinicRoleViewSet(ClinicViewSet):
    queryset = ClinicRole.objects.all()
    serializer_class = ClinicRoleSerializer
    permission_classes = [ReadOnlyForNonAdmin]
    branch_field = None
    ordering = ["name"]


class StaffUserViewSet(ClinicViewSet):
    """The clinic's own user accounts.

    `User` is not a `TenantOwnedModel` — it carries a nullable tenant, because
    platform staff belong to no clinic — so the tenant filter that the base
    class gets for free from `TenantManager` has to be written out here. It is
    the one place in the API where that is true, and getting it wrong would
    list every user of every clinic.
    """

    queryset = User.objects.all()
    serializer_class = StaffUserSerializer
    permission_classes = [IsClinicAdmin]
    branch_field = None
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["username", "email", "first_name", "last_name"]
    ordering = ["username"]

    def get_queryset(self):
        tenant = get_current_tenant()
        if tenant is None:
            return User.objects.none()
        return (
            User.objects.filter(tenant=tenant)
            # Platform operators are never clinic staff and must not appear in
            # a clinic's user list, let alone be editable from it.
            .filter(is_platform_staff=False, is_superuser=False)
            .select_related("role", "branch")
            .order_by("username")
        )

    def perform_create(self, serializer):
        tenant = get_current_tenant()
        serializer.save(tenant=tenant, clinic_code=(tenant.slug or "")[:20].upper())

    def perform_destroy(self, instance):
        """Deactivate rather than delete.

        Staff accounts are referenced by every audit entry, appointment and
        expense they ever created; removing the row either fails on a PROTECT
        or orphans the history that makes those records accountable.
        """
        instance.is_active = False
        instance.save(update_fields=["is_active"])
