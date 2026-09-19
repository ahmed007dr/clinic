"""Which services each clinic offers — management's switch (docs/15, D9).

    GET /api/branch-services/?branch=<uuid>   every service of the group, and whether this clinic
                                              offers it / takes online bookings for it / has a doctor ready
    PUT /api/branch-services/                 `{branch, service, enabled, online_bookable}` — switch one on or off

The Owner works on any clinic; a clinic's Admin only on their own (another
clinic's uuid is a 404). Switching a service off keeps the row, so its online
setting is remembered and the public page simply stops listing it. This is
separate from the doctors' contracts: enabling a service here does not put a
doctor under contract, and a contract does not enable the service.
"""

from collections import Counter

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.roles import sees_all_branches
from api.permissions import IsClinicAdmin
from branches.models import Branch
from services.catalog import qualified_pairs
from services.models import BranchService, Service


def _branches_for(user):
    queryset = Branch.objects.all()
    if sees_all_branches(user):
        return queryset
    return queryset.filter(pk=user.branch_id) if user.branch_id else queryset.none()


class BranchServicesView(APIView):
    permission_classes = [IsClinicAdmin]

    def _branch(self, request, uuid):
        branches = _branches_for(request.user)
        if uuid:
            return get_object_or_404(branches, uuid=uuid)
        # No clinic named: an Admin's own, the Owner's first.
        return branches.order_by("name").first()

    def get(self, request):
        branches = list(_branches_for(request.user).order_by("name"))
        branch = self._branch(request, request.query_params.get("branch"))
        if branch is None:
            return Response({"branch": None, "branches": [], "services": []})

        rows = {row.service_id: row for row in BranchService.objects.filter(branch=branch)}
        ready = Counter(rate.service_id for _b, rate in qualified_pairs(branch_ids={branch.pk}))
        services = Service.objects.select_related("specialization").order_by("name")
        return Response({
            "branch": {"uuid": str(branch.uuid), "name": branch.name},
            "branches": [{"uuid": str(b.uuid), "name": b.name} for b in branches],
            "services": [
                {
                    "uuid": str(service.uuid),
                    "name": service.name,
                    "specialization": service.specialization.name if service.specialization_id else None,
                    "base_price": str(service.base_price),
                    "duration_minutes": service.duration_minutes,
                    "price_display": service.price_display,
                    # A stopped service is off everywhere, whatever this clinic says.
                    "service_active": service.is_active,
                    "enabled": bool(rows.get(service.pk) and rows[service.pk].is_active),
                    "online_bookable": rows[service.pk].online_bookable if service.pk in rows else True,
                    # Doctors under contract for it here who could take a booking now.
                    "doctors_ready": ready.get(service.pk, 0),
                }
                for service in services
            ],
        })

    @transaction.atomic
    def put(self, request):
        branch = get_object_or_404(_branches_for(request.user), uuid=request.data.get("branch"))
        service = get_object_or_404(Service.objects.all(), uuid=request.data.get("service"))
        enabled = request.data.get("enabled")
        online = request.data.get("online_bookable")
        if enabled is not None and not isinstance(enabled, bool):
            return Response({"enabled": ["true أو false."]}, status=400)
        if online is not None and not isinstance(online, bool):
            return Response({"online_bookable": ["true أو false."]}, status=400)

        row = BranchService.objects.filter(branch=branch, service=service).first()
        if row is None:
            row = BranchService(
                tenant=request.user.tenant, branch=branch, service=service,
                is_active=True if enabled is None else enabled,
            )
        elif enabled is not None:
            row.is_active = enabled
        if online is not None:
            row.online_bookable = online
        row.save()
        return Response({
            "branch": str(branch.uuid), "service": str(service.uuid),
            "enabled": row.is_active, "online_bookable": row.online_bookable,
        })
