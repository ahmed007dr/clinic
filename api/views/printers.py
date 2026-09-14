"""Printer inventory — which physical printer is which, per branch.

Read by anyone in the clinic (so reception can tell one printer's role from
another when a branch has more than one); changed by the Admin/Owner only,
same as any other reference list (PaymentMethod, ExpenseCategory).
"""

from api.permissions import ReadOnlyForNonAdmin
from api.serializers.printers import PrinterSerializer
from api.viewsets import ClinicViewSet
from branches.models import Printer


class PrinterViewSet(ClinicViewSet):
    queryset = Printer.objects.all()
    serializer_class = PrinterSerializer
    permission_classes = [ReadOnlyForNonAdmin]
    ordering = ["branch__name", "purpose", "name"]

    def filter_tenant_queryset(self, queryset):
        queryset = queryset.select_related("branch")
        purpose = self.request.query_params.get("purpose")
        if purpose:
            queryset = queryset.filter(purpose=purpose)
        return queryset
