"""Branches, services and staff — the reference data everything else points at."""

from django.utils import timezone
from rest_framework import serializers

from api.relations import TenantScopedRelatedField
from branches.models import Branch
from employees.models import Employee, EmployeeType, SalaryType, Specialization
from services.models import Service

from .common import ClinicSerializer


class BranchSerializer(ClinicSerializer):
    class Meta:
        model = Branch
        fields = [
            "uuid", "name", "code", "address", "phone", "email", "footer_text",
            # Stopped by the Owner (branches.Branch.is_active).
            "is_active",
        ]


class BranchAboutSerializer(ClinicSerializer):
    """What the portal tells the public about a branch — and nothing else of it.
    The name and whether it runs are the Owner's, through BranchSerializer."""

    name = serializers.CharField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    # Left out of the portal's "About" tab: the whole branch (`about_visible`),
    # or chosen specialties of it. Written as UUIDs of this clinic's specialties.
    hidden_specializations = TenantScopedRelatedField(
        model=Specialization, many=True, required=False, source="about_hidden_specialties"
    )
    specializations = serializers.SerializerMethodField()

    class Meta:
        model = Branch
        fields = [
            "uuid", "name", "is_active",
            "about_visible", "hidden_specializations",
            # A website booking here is confirmed at once instead of waiting
            # for the clinic's call (docs/15, D3).
            "online_booking_confirms_at_once", "online_cancel_notice_hours",
            "address", "phone", "map_url", "working_hours", "about_text",
            "specializations",
        ]

    def get_specializations(self, branch):
        """Every specialty of the branch's doctors (branches.about), each marked
        `hidden` when this branch left it out of the portal. Read-only: they are
        worked out, not typed."""
        hidden = {str(s.uuid) for s in branch.about_hidden_specialties.all()}
        return [
            {**item, "hidden": item["uuid"] in hidden}
            for item in self.context.get("specialties", {}).get(branch.pk, [])
        ]

    def validate_map_url(self, value):
        # A link the public will click: web pages only, never `javascript:`.
        if value and not value.lower().startswith(("http://", "https://")):
            raise serializers.ValidationError("الرابط يجب أن يبدأ بـ https://")
        return value


class EmployeeTypeSerializer(ClinicSerializer):
    class Meta:
        model = EmployeeType
        fields = ["uuid", "name", "description"]


class SpecializationSerializer(ClinicSerializer):
    class Meta:
        model = Specialization
        fields = ["uuid", "name", "description"]


class SalaryTypeSerializer(ClinicSerializer):
    class Meta:
        model = SalaryType
        fields = ["uuid", "name"]


class ServiceSerializer(ClinicSerializer):
    specialization = TenantScopedRelatedField(
        model=Specialization, required=False, allow_null=True
    )
    specialization_name = serializers.CharField(
        source="specialization.name", read_only=True, default=None
    )

    class Meta:
        model = Service
        fields = [
            "uuid", "name", "description",
            "specialization", "specialization_name", "base_price",
            # What the public page says about it (docs/15): how long a session
            # takes, and whether the price is final, a floor or set after
            # evaluation.
            "duration_minutes", "price_display",
            # Sold by quantity (docs/15): the price is then per unit and a booking
            # asks for how many. Management's to set.
            "requires_quantity", "doctor_sets_quantity", "quantity_unit", "min_quantity", "max_quantity",
            # Stopped by management: out of every picker (api/views/core.py).
            "is_active",
        ]

    def validate(self, attrs):
        attrs = super().validate(attrs)

        def value(name, default=None):
            return attrs[name] if name in attrs else getattr(self.instance, name, default)

        if value("requires_quantity", False):
            minimum, maximum = value("min_quantity"), value("max_quantity")
            if minimum is None or minimum <= 0:
                raise serializers.ValidationError({"min_quantity": "أقل كمية أكبر من صفر."})
            if maximum is not None and maximum < minimum:
                raise serializers.ValidationError({"max_quantity": "أكبر كمية لا تقل عن أقل كمية."})
        return attrs


class EmployeeSerializer(ClinicSerializer):
    employee_type = TenantScopedRelatedField(
        model=EmployeeType, required=False, allow_null=True
    )
    branch = TenantScopedRelatedField(model=Branch)
    salary_type = TenantScopedRelatedField(
        model=SalaryType, required=False, allow_null=True
    )
    specializations = TenantScopedRelatedField(
        model=Specialization, many=True, required=False
    )
    # Further clinics a doctor works in. Owner only (validate_extra_branches).
    extra_branches = TenantScopedRelatedField(model=Branch, many=True, required=False)

    # The model defaults this to `timezone.now`, which is a *datetime*: an
    # employee created without a hire date then held a datetime in a DateField
    # and the response failed to render. A date, from the start.
    hire_date = serializers.DateField(default=lambda: timezone.now().date())

    employee_type_name = serializers.CharField(
        source="employee_type.name", read_only=True, default=None
    )
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    specialization_names = serializers.SerializerMethodField()
    extra_branch_names = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = [
            "uuid", "serial_number", "name",
            "employee_type", "employee_type_name",
            "branch", "branch_name",
            "national_id", "phone1", "phone2", "email",
            "hire_date", "salary_type", "salary_value",
            "specializations", "specialization_names",
            "extra_branches", "extra_branch_names",
            # The doctor's default share of what is paid (billing.pricing).
            "commission_percent",
            # Whether the doctor is shown on the public page (docs/15).
            "show_publicly",
        ]

    def get_specialization_names(self, employee):
        return [s.name for s in employee.specializations.all()]

    def get_extra_branch_names(self, employee):
        return [b.name for b in employee.extra_branches.all()]

    def validate_extra_branches(self, branches):
        """Linking a doctor to another clinic opens that clinic's patients to
        the doctor's login, which is a group decision: the Owner's alone. A
        clinic Admin sending the field unchanged is fine; changing it is not."""
        from accounts.roles import is_owner

        current = set(self.instance.extra_branches.values_list("pk", flat=True)) if self.instance else set()
        wanted = {b.pk for b in branches}
        if wanted != current and not is_owner(self.request_user):
            raise serializers.ValidationError("ربط الطبيب بفروع أخرى من صلاحية صاحب المجمع فقط.")
        # The home branch is already theirs; listing it again is noise.
        home = self.initial_data.get("branch") or (
            self.instance.branch.uuid if self.instance and self.instance.branch_id else None
        )
        return [b for b in branches if str(b.uuid) != str(home)]


class DoctorBriefSerializer(ClinicSerializer):
    """Doctors only, for the pickers on appointment and clinical forms.

    A separate serializer rather than a filtered `EmployeeSerializer` because
    the pickers must not leak salary figures to whoever is booking a visit.
    """

    branch = serializers.SlugRelatedField(slug_field="uuid", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    # So a picker can narrow doctors to a specialty without a second request.
    specializations = serializers.SlugRelatedField(slug_field="uuid", many=True, read_only=True)
    # Shown to management only, to tell two doctors apart when searching by
    # phone; whoever is merely booking a visit has no need of it.
    phone1 = serializers.SerializerMethodField()

    def get_phone1(self, employee):
        from accounts.roles import is_clinic_admin

        return employee.phone1 if is_clinic_admin(self.request_user) else None

    class Meta:
        model = Employee
        fields = ["uuid", "name", "phone1", "branch", "branch_name", "specializations"]
        read_only_fields = fields
