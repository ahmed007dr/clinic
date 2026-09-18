"""The "About the clinic" text of each branch, for management to edit.

    GET   /api/about/            the branches you may edit — the Owner's: every one,
                                 a branch Admin's: their own
    PATCH /api/about/<uuid>/     address, phone, map link, working hours, description

What the patient portal shows is `portal.registration.PublicAboutView`. A
separate endpoint from `/api/branches/` on purpose: that one is the Owner's and
changes the clinic itself (its name, code, whether it runs); this one only
changes what the public is told, and so can be given to a branch's Admin without
giving them the rest.
"""

from rest_framework.filters import OrderingFilter, SearchFilter

from accounts.roles import sees_all_branches
from api.permissions import IsClinicAdmin
from api.serializers.core import BranchAboutSerializer
from api.viewsets import ClinicViewSet
from branches.about import specialties_by_branch
from branches.models import Branch


class BranchAboutViewSet(ClinicViewSet):
    queryset = Branch.objects.all()
    serializer_class = BranchAboutSerializer
    permission_classes = [IsClinicAdmin]
    # Scoped by hand below: the Owner's reach is the group, an Admin's is one branch.
    branch_field = None
    http_method_names = ["get", "patch", "head", "options"]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["name", "address"]
    ordering = ["name"]

    def filter_tenant_queryset(self, queryset):
        user = self.request.user
        if sees_all_branches(user):
            return queryset
        return queryset.filter(pk=user.branch_id) if user.branch_id else queryset.none()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["specialties"] = specialties_by_branch()
        return context
