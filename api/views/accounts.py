"""Staff accounts and clinic roles — Admin only."""

from django.contrib.auth import get_user_model
from rest_framework.filters import OrderingFilter, SearchFilter

from accounts.models import ClinicRole
from rest_framework.exceptions import PermissionDenied

from accounts.roles import OWNER, can_manage_account, scope_queryset_to_user, sees_all_branches
from api.permissions import IsClinicAdmin, ReadOnlyForNonOwner
from api.serializers.accounts import ClinicRoleSerializer, StaffUserSerializer
from api.viewsets import ClinicViewSet
from tenants.context import get_current_tenant

User = get_user_model()


class ClinicRoleViewSet(ClinicViewSet):
    queryset = ClinicRole.objects.all()
    serializer_class = ClinicRoleSerializer
    # Roles are the group's structure: only the Owner reshapes them.
    permission_classes = [ReadOnlyForNonOwner]
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
        queryset = (
            User.objects.filter(tenant=tenant)
            # Platform operators are never clinic staff and must not appear in
            # a clinic's user list, let alone be editable from it.
            .filter(is_platform_staff=False, is_superuser=False)
            .select_related("role", "branch")
            .order_by("username")
        )
        if not sees_all_branches(self.request.user):
            # A clinic Admin manages their own clinic, and never an Owner —
            # who could otherwise be reset or deactivated from below.
            queryset = scope_queryset_to_user(queryset, self.request.user).exclude(role__name=OWNER)
        return queryset

    def perform_create(self, serializer):
        tenant = get_current_tenant()
        extra = {}
        if not sees_all_branches(self.request.user):
            extra["branch"] = self.request.user.branch
        serializer.save(tenant=tenant, clinic_code=(tenant.slug or "")[:20].upper(), **extra)

    def check_can_manage(self, target):
        if not can_manage_account(self.request.user, target):
            raise PermissionDenied(
                "لا يمكنك تعديل هذا الحساب أو إيقافه: الأدمن يدير حسابات الموظفين والأطباء "
                "في فرعه، وصاحب المجمع يدير الجميع، ولا أحد يوقف حسابه بنفسه."
            )

    def perform_update(self, serializer):
        self.check_can_manage(serializer.instance)
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        """Deactivate rather than delete.

        Staff accounts are referenced by every audit entry, appointment and
        expense they ever created; removing the row either fails on a PROTECT
        or orphans the history that makes those records accountable.
        """
        self.check_can_manage(instance)
        instance.is_active = False
        instance.save(update_fields=["is_active"])
