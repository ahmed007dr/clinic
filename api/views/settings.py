"""Clinic-level settings a clinic Admin controls. Currently: the patient portal."""

from rest_framework.response import Response
from rest_framework.views import APIView

from api.permissions import IsGroupOwner
from tenants.context import get_current_tenant


class ClinicSettingsView(APIView):
    # Group-wide settings: the owner's call.
    permission_classes = [IsGroupOwner]

    def payload(self, request, tenant):
        return {
            "portal_show_diagnosis": tenant.portal_show_diagnosis,
            "portal_self_registration": tenant.portal_self_registration,
            "registration_url": request.build_absolute_uri(f"/app/portal/{tenant.slug}/register"),
            "portal_url": request.build_absolute_uri(f"/app/portal/{tenant.slug}/"),
        }

    def get(self, request):
        return Response(self.payload(request, get_current_tenant()))

    def patch(self, request):
        tenant = get_current_tenant()
        changed = []
        for field in ("portal_show_diagnosis", "portal_self_registration"):
            value = request.data.get(field)
            if value is None:
                continue
            # A real boolean only: bool("false") is True, and these switches
            # decide what patients read and whether the public can register.
            if not isinstance(value, bool):
                return Response({field: ["قيمة غير صالحة."]}, status=400)
            setattr(tenant, field, value)
            changed.append(field)
        if changed:
            tenant.save(update_fields=changed)
        return Response(self.payload(request, tenant))
