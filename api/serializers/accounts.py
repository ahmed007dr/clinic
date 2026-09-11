"""The signed-in user, as the SPA needs to see them."""

from django.contrib.auth import get_user_model
from rest_framework import serializers

from accounts.models import ClinicRole
from accounts.roles import (
    assignable_role_names,
    current_branch_id,
    doctor_branch_ids,
    is_doctor,
    is_front_desk,
    is_owner,
)
from api.permissions import can_view_clinical, is_clinic_admin
from billing.access import can_view_finance
from billing.shifts import manages_shifts, works_in_shifts
from api.relations import TenantScopedRelatedField
from branches.models import Branch
from employees.models import Employee

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
    # The doctor record this login is — what a new visit or prescription is
    # signed with, and what "my patients" means. Null for everyone else.
    doctor = serializers.SerializerMethodField()
    # A doctor linked to several clinics: which ones, and which is showing.
    branches = serializers.SerializerMethodField()
    active_branch = serializers.SerializerMethodField()

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
            "doctor",
            "branches",
            "active_branch",
        ]
        read_only_fields = fields

    def get_branches(self, user):
        ids = doctor_branch_ids(user)
        if len(ids) < 2:
            return []
        return BranchBriefSerializer(Branch.objects.filter(pk__in=ids).order_by("name"), many=True).data

    def get_active_branch(self, user):
        branch_id = current_branch_id(user)
        if not branch_id:
            return None
        branch = Branch.objects.filter(pk=branch_id).first()
        return BranchBriefSerializer(branch).data if branch else None

    def get_doctor(self, user):
        employee = user.employee if is_doctor(user) else None
        return {"uuid": str(employee.uuid), "name": employee.name} if employee else None

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
            # The books over time: reports, month totals, the revenue chart
            # (billing.access). Reception handles today's money, not these.
            "view_finance": can_view_finance(user),
            "manage_staff": admin,
            "manage_settings": owner,
            # Clinic-wide rather than one branch — drives whether the UI offers
            # a branch filter at all.
            "all_branches": owner,
            "is_doctor": is_doctor(user),
            # Records money inside a cash shift / reviews everyone's shifts.
            "works_in_shifts": works_in_shifts(user),
            "manage_shifts": manages_shifts(user),
            # Doctor contracts and shares: management's, and a doctor's own.
            "view_contracts": admin or is_doctor(user),
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
    # Which doctor a Doctor account is (accounts.User.employee).
    employee = TenantScopedRelatedField(model=Employee, required=False, allow_null=True)
    employee_name = serializers.CharField(
        source="employee.name", read_only=True, default=None
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
            "employee",
            "employee_name",
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
        self.validate_employee_link(attrs)
        return attrs

    def validate_employee_link(self, attrs):
        """The link decides whose patients a doctor sees, so a wrong one is a
        data leak, not a typo: one record per account, in the account's own
        clinic, and only on a Doctor account."""
        instance = self.instance
        role = attrs.get("role", getattr(instance, "role", None))
        if getattr(role, "name", None) != "Doctor":
            if attrs.get("employee") is not None:
                raise serializers.ValidationError(
                    {"employee": "الربط بسجل طبيب متاح لحسابات الأطباء فقط."}
                )
            # A doctor moved to another role stops being that doctor.
            if getattr(instance, "employee_id", None):
                attrs["employee"] = None
            return
        employee = attrs.get("employee", getattr(instance, "employee", None))
        if employee is None:
            return
        branch = attrs.get("branch", getattr(instance, "branch", None))
        if branch is not None and employee.branch_id != branch.pk:
            raise serializers.ValidationError(
                {"employee": "سجل الطبيب تابع لفرع آخر غير فرع الحساب."}
            )
        taken = User.objects.filter(employee=employee)
        if instance is not None:
            taken = taken.exclude(pk=instance.pk)
        if taken.exists():
            raise serializers.ValidationError(
                {"employee": "سجل الطبيب هذا مرتبط بحساب آخر بالفعل."}
            )

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
