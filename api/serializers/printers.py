"""A branch's registered printers — inventory, not routing (branches.models.Printer)."""

from rest_framework import serializers

from api.relations import TenantScopedRelatedField
from branches.models import Branch, Printer

from .common import ClinicSerializer


class PrinterSerializer(ClinicSerializer):
    branch = TenantScopedRelatedField(model=Branch)
    branch_name = serializers.CharField(source="branch.name", read_only=True)

    class Meta:
        model = Printer
        fields = [
            "uuid", "branch", "branch_name", "name", "purpose", "purpose_display",
            "is_default", "is_active", "ip_address", "mac_address", "subnet_mask",
            "gateway", "dhcp", "port", "notes",
        ]

    purpose_display = serializers.CharField(source="get_purpose_display", read_only=True)

    def validate(self, attrs):
        # A default printer settles which one the reception screen offers
        # first for its purpose; two defaults would make that arbitrary.
        branch = attrs.get("branch") or getattr(self.instance, "branch", None)
        purpose = attrs.get("purpose") or getattr(self.instance, "purpose", None)
        is_default = attrs.get("is_default", getattr(self.instance, "is_default", False))
        if is_default and branch is not None and purpose is not None:
            clash = Printer.objects.filter(branch=branch, purpose=purpose, is_default=True)
            if self.instance is not None:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise serializers.ValidationError(
                    {"is_default": "توجد بالفعل طابعة افتراضية لهذا الفرع ولهذا الغرض."}
                )
        return attrs
