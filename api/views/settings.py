"""Clinic-level settings a clinic Admin controls. Currently: the patient portal."""

from rest_framework.response import Response
from rest_framework.views import APIView

from api.permissions import IsClinicAdmin
from tenants.context import get_current_tenant


class ClinicSettingsView(APIView):
    permission_classes = [IsClinicAdmin]

    def payload(self, request, tenant):
        return {
            "portal_show_diagnosis": tenant.portal_show_diagnosis,
            "portal_url": request.build_absolute_uri(f"/app/portal/{tenant.slug}/"),
        }

    def get(self, request):
        return Response(self.payload(request, get_current_tenant()))

    def patch(self, request):
        tenant = get_current_tenant()
        value = request.data.get("portal_show_diagnosis")
        if value is not None:
            # A real boolean only: bool("false") is True, and this switch
            # decides whether patients read their diagnosis.
            if not isinstance(value, bool):
                return Response({"portal_show_diagnosis": ["قيمة غير صالحة."]}, status=400)
            tenant.portal_show_diagnosis = value
            tenant.save(update_fields=["portal_show_diagnosis"])
        return Response(self.payload(request, tenant))
