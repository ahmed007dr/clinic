"""A clinic's printed look — letterhead and intake form (branches/printing.py).

    GET   /api/branches/<uuid>/print-settings/
    PATCH /api/branches/<uuid>/print-settings/   JSON, or multipart with `logo`

Its own endpoint rather than part of the branch record because the audience
differs: a branch's name, code and whether it runs are the Owner's; how its
paper looks, and the address and phone printed on it, are also its own
Admin's (the group owner's rule, 2026-09-11).
"""

from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.roles import current_branch_id, is_clinic_admin, sees_all_branches
from api.permissions import IsClinicMember
from branches.models import Branch
from branches.printing import (
    HEX,
    INTAKE_SECTIONS,
    LINK_KINDS,
    LinkError,
    clean_links,
    intake_layout,
    letterhead,
)

MAX_LOGO_BYTES = 1024 * 1024
LOGO_FORMATS = {"PNG", "JPEG", "WEBP"}


class PrintSettingsSerializer(serializers.ModelSerializer):
    logo = serializers.ImageField(required=False, allow_null=True, write_only=True)
    remove_logo = serializers.BooleanField(required=False, write_only=True)

    class Meta:
        model = Branch
        fields = [
            "address", "phone", "email", "footer_text", "logo", "remove_logo",
            "print_header_title", "print_header_subtitle", "print_accent_color",
            "print_logo_in_footer", "intake_form_title", "intake_form_intro",
            "intake_consent_text", "intake_sections", "intake_extra_fields",
            "print_links",
        ]

    def validate_logo(self, logo):
        if logo is None:
            return logo
        if logo.size > MAX_LOGO_BYTES:
            raise serializers.ValidationError("حجم الشعار أكبر من ١ ميجابايت.")
        # ImageField already made Pillow open it; only raster formats a
        # browser prints reliably — never SVG, which can carry script.
        image = getattr(logo, "image", None)
        if image is None or getattr(image, "format", None) not in LOGO_FORMATS:
            raise serializers.ValidationError("الشعار يجب أن يكون صورة PNG أو JPG أو WEBP.")
        return logo

    def validate_print_accent_color(self, value):
        if value and not HEX.match(value):
            raise serializers.ValidationError("اللون بصيغة #RRGGBB.")
        return value

    def validate_intake_sections(self, value):
        if not isinstance(value, list) or any(key not in INTAKE_SECTIONS for key in value):
            raise serializers.ValidationError("أقسام غير معروفة.")
        return value

    def validate_print_links(self, value):
        try:
            return clean_links(value)
        except LinkError as error:
            raise serializers.ValidationError(str(error))

    def validate_intake_extra_fields(self, value):
        if not isinstance(value, list) or len(value) > 20:
            raise serializers.ValidationError("حتى ٢٠ سطراً إضافياً.")
        return [str(label).strip()[:80] for label in value if str(label).strip()]

    def update(self, instance, validated_data):
        if validated_data.pop("remove_logo", False):
            instance.logo = None
        logo = validated_data.pop("logo", None)
        if logo is not None:
            instance.logo = logo
        return super().update(instance, validated_data)


class PrintSettingsView(APIView):
    permission_classes = [IsClinicMember]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def branch(self, request, uuid):
        branch = get_object_or_404(Branch, uuid=uuid)
        allowed = sees_all_branches(request.user) or (
            is_clinic_admin(request.user) and branch.pk == current_branch_id(request.user)
        )
        if not allowed:
            raise PermissionDenied("تصميم المطبوعات لإدارة الفرع أو صاحب المجمع.")
        return branch

    def payload(self, request, branch):
        data = PrintSettingsSerializer(branch).data
        data.update({
            "branch": str(branch.uuid),
            "branch_name": branch.name,
            "logo_url": letterhead(branch, request)["logo_url"],
            "available_sections": [{"key": k, "label": v} for k, v in INTAKE_SECTIONS.items()],
            "effective_sections": intake_layout(branch)["sections"],
            "link_kinds": [{"key": k, "label": v} for k, v in LINK_KINDS.items()],
        })
        return data

    def get(self, request, uuid):
        return Response(self.payload(request, self.branch(request, uuid)))

    def patch(self, request, uuid):
        branch = self.branch(request, uuid)
        serializer = PrintSettingsSerializer(branch, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(self.payload(request, branch))
