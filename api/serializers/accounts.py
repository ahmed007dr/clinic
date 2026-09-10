"""The signed-in user, as the SPA needs to see them."""

from django.contrib.auth import get_user_model
from rest_framework import serializers

from accounts.models import ClinicRole
from accounts.roles import assignable_role_names, is_front_desk, is_owner
from api.permissions import can_view_clinical, is_clinic_admin
from api.relations import TenantScopedRelatedField
from branches.models import Branch

from .common import ClinicSerializer

User = get_user_model()


class ClinicRoleSerializer(ClinicSerializer):
    class Meta:
        model = ClinicRole
        fields = ["uuid", "name", "description"]


class BranchBriefSerializer(ClinicSerializer):
    """Just enough to label a branch. The full serializer lives in core.py."""

    class Meta:
        model = Branch
        fields = ["uuid", "name", "code"]


class CurrentUserSerializer(serializers.ModelSerializer):
    """The session payload: who you are, where you work, what you may do.

    `permissions` is a convenience for the interface — it decides which nav
    items and buttons to draw. **It is not the boundary.** Every one of these
    flags is re-derived server-side on each request by the permission classes
    in `api/permissions.py`; a client that flips them in devtools gets a 403,
    not access. It is here so the UI does not have to guess, not so the server
    can stop checking.
    """

    role = serializers.CharField(source="role.name", read_only=True, default=None)
    branch = BranchBriefSerializer(read_only=True)
    clinic = serializers.CharField(source="tenant.name", read_only=True, default=None)
    clinic_status = serializers.CharField(
        source="tenant.status", read_only=True, default=None
    )
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "uuid",
            "username",
            "email",
            "first_name",
            "last_name",
            "role",
            "branch",
            "clinic",
            "clinic_status",
            "permissions",
        ]
        read_only_fields = fields

    def get_permissions(self, user):
        admin = is_clinic_admin(user)
        owner = is_owner(user)
        return {
            "is_admin": admin,
            # The group owner: every clinic, the group dashboard, the plan.
            "is_owner": owner,
            "front_desk": is_front_desk(user),
            "view_clinical": can_view_clinical(user),
            # Reception handles money and bookings; clinical staff do not need
            # the expense ledger to do their job.
            "manage_billing": admin or getattr(user.role, "name", None) == "Reception",
            "manage_staff": admin,
            "manage_settings": owner,
            # Clinic-wide rather than one branch — drives whether the UI offers
            # a branch filter at all.
            "all_branches": owner,
        }


class StaffUserSerializer(ClinicSerializer):
    """Staff accounts, as managed by a clinic Admin.

    Password is write-only and optional on update, so editing a colleague's
    branch does not require resetting their password.
    """

    role = TenantScopedRelatedField(model=ClinicRole, required=False, allow_null=True)
    branch = TenantScopedRelatedField(model=Branch, required=False, allow_null=True)
    role_name = serializers.CharField(source="role.name", read_only=True, default=None)
    branch_name = serializers.CharField(
        source="branch.name", read_only=True, default=None
    )
    password = serializers.CharField(
        write_only=True, required=False, allow_blank=True, min_length=8, style={"input_type": "password"}
    )

    class Meta:
        model = User
        fields = [
            "uuid",
            "username",
            "email",
            "first_name",
            "last_name",
            "role",
            "role_name",
            "branch",
            "branch_name",
            "is_active",
            "password",
        ]

    def get_fields(self):
        fields = super().get_fields()
        # ClinicSerializer strips `tenant`; `is_platform_staff` and
        # `is_superuser` are deliberately absent from `Meta.fields` — a clinic
        # admin must not be able to grant either.
        return fields

    def validate(self, attrs):
        """A clinic Admin staffs their own clinic, and never creates an Owner.

        Without this the staff screen would be the shortest path from running
        one clinic to seeing every clinic's books.
        """
        actor = self.request_user
        role = attrs.get("role")
        if role is not None and role.name not in assignable_role_names(actor):
            raise serializers.ValidationError({"role": "لا يمكنك منح هذا الدور."})
        branch = attrs.get("branch")
        if branch is not None and not is_owner(actor) and branch.pk != getattr(actor, "branch_id", None):
            raise serializers.ValidationError({"branch": "يمكنك إدارة موظفي عيادتك فقط."})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password", "") or ""
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            # No usable password rather than a blank one: the account exists
            # and cannot be signed into until an admin sets a password.
            user.set_unusable_password()
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", "") or ""
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(style={"input_type": "password"}, trim_whitespace=False)


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(trim_whitespace=False)
    new_password = serializers.CharField(min_length=8, trim_whitespace=False)
