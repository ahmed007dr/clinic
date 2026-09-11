"""Payments, expenses and the financial report."""

from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from api.permissions import (
    ChangeRequiresAdmin,
    IsClinicAdmin,
    IsClinicMember,
    IsFrontDesk,
    ReadOnlyForNonAdmin,
    WriteRequiresFrontDesk,
    is_clinic_admin,
    sees_all_branches,
)
from billing.access import (
    restrict_expenses,
    restrict_payments,
    visible_expenses,
    visible_payments,
)
from api.serializers.billing import (
    ExpenseCategorySerializer,
    ExpenseSerializer,
    PaymentMethodSerializer,
    PaymentSerializer,
)
from api.viewsets import ClinicViewSet
from billing.models import Expense, ExpenseCategory, Payment, PaymentMethod
from billing.shifts import ShiftError, shift_for_recording
from billing.voiding import VoidError, void
from branches.models import Branch


def _date_range(params):
    return params.get("from"), params.get("to")


class RecordedInShiftMixin:
    """New money goes into the recorder's open cash shift (billing.shifts).

    The shift, its clinic, and who recorded it are stamped here, never taken
    from input; with no open shift the request is refused with the reason.
    """

    def base_queryset(self):
        # `?voided=1`: management reviewing what was cancelled. Everyone else,
        # and every other request, sees only money that still counts.
        model = self.queryset.model
        if self.request.query_params.get("voided") == "1" and is_clinic_admin(self.request.user):
            return model.objects.with_voided().filter(voided_at__isnull=False)
        return model.objects.all()

    @action(detail=True, methods=["post"], url_path="void")
    def void(self, request, uuid=None):
        """`{reason}` — cancel it: kept on record, out of every total."""
        record = self.get_object()
        try:
            void(request.user, record, request.data.get("reason"))
        except VoidError as error:
            raise ValidationError({"detail": str(error)})
        return Response(self.get_serializer(record).data)

    def creation_fields(self):
        try:
            shift = shift_for_recording(self.request.user)
        except ShiftError as error:
            raise ValidationError({"detail": str(error)})
        if shift is None:
            return {}
        return {"shift": shift, "branch": shift.branch}

    def perform_update(self, serializer):
        # Correcting a recorded amount never moves it to another drawer.
        serializer.save()


class PaymentMethodViewSet(ClinicViewSet):
    queryset = PaymentMethod.objects.all()
    serializer_class = PaymentMethodSerializer
    permission_classes = [ReadOnlyForNonAdmin]
    branch_field = None
    ordering = ["name"]


class ExpenseCategoryViewSet(ClinicViewSet):
    queryset = ExpenseCategory.objects.all()
    serializer_class = ExpenseCategorySerializer
    permission_classes = [ReadOnlyForNonAdmin]
    branch_field = None
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["name"]
    ordering = ["name"]


class PaymentViewSet(RecordedInShiftMixin, ClinicViewSet):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    # The front desk records a payment; only an admin may change or remove
    # one. What each role may *read* is billing.access's decision.
    permission_classes = [IsClinicMember, WriteRequiresFrontDesk, ChangeRequiresAdmin]
    created_by_field = "created_by"
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["receipt_number", "patient__name", "appointment__serial_number"]
    ordering_fields = ["date", "amount", "receipt_number"]
    ordering = ["-date"]

    def filter_tenant_queryset(self, queryset):
        queryset = restrict_payments(queryset, self.request.user)
        queryset = queryset.select_related("patient", "method", "branch", "appointment")
        date_from, date_to = _date_range(self.request.query_params)
        if date_from:
            queryset = queryset.filter(date__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(date__date__lte=date_to)
        branch = self.request.query_params.get("branch")
        if branch:
            queryset = queryset.filter(branch__uuid=branch)
        patient = self.request.query_params.get("patient")
        if patient:
            queryset = queryset.filter(patient__uuid=patient)
        return queryset


class ExpenseViewSet(RecordedInShiftMixin, ClinicViewSet):
    queryset = Expense.objects.all()
    serializer_class = ExpenseSerializer
    # The same audience the expenses screen is shown to (manage_billing).
    permission_classes = [IsFrontDesk]
    created_by_field = "created_by"
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["notes", "category__name", "employee__name"]
    ordering_fields = ["date", "amount"]
    ordering = ["-date"]

    def creation_fields(self):
        extra = super().creation_fields()
        if extra:
            # Inside a shift the date is the day it was paid out, not a
            # field: a back-dated expense would land in a closed day's books.
            extra["date"] = timezone.now().date()
        return extra

    def filter_tenant_queryset(self, queryset):
        queryset = restrict_expenses(queryset, self.request.user)
        queryset = queryset.select_related("branch", "category", "employee")
        date_from, date_to = _date_range(self.request.query_params)
        if date_from:
            queryset = queryset.filter(date__gte=date_from)
        if date_to:
            queryset = queryset.filter(date__lte=date_to)
        branch = self.request.query_params.get("branch")
        if branch:
            queryset = queryset.filter(branch__uuid=branch)
        category = self.request.query_params.get("category")
        if category:
            queryset = queryset.filter(category__uuid=category)
        return queryset


class FinancialReportView(ClinicViewSet):
    """Revenue against expenses, over a period, for whatever the caller may see.

    Management only (billing.access): a period report is exactly the "every
    balance on any date" view the front desk must not have. An Admin's figures
    still cover their own clinic only.
    """

    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    permission_classes = [IsClinicAdmin]
    http_method_names = ["get", "head", "options"]
    pagination_class = None

    def list(self, request):
        params = request.query_params
        date_from, date_to = _date_range(params)
        branch = params.get("branch")

        payments = visible_payments(request.user, Payment.objects.all())
        expenses = visible_expenses(request.user, Expense.objects.all())

        if date_from:
            payments = payments.filter(date__date__gte=date_from)
            expenses = expenses.filter(date__gte=date_from)
        if date_to:
            payments = payments.filter(date__date__lte=date_to)
            expenses = expenses.filter(date__lte=date_to)
        if branch:
            payments = payments.filter(branch__uuid=branch)
            expenses = expenses.filter(branch__uuid=branch)

        revenue = payments.aggregate(total=Sum("amount"), count=Count("id"))
        spend = expenses.aggregate(total=Sum("amount"), count=Count("id"))
        total_revenue = revenue["total"] or 0
        total_expenses = spend["total"] or 0

        by_branch = []
        if sees_all_branches(request.user):
            # Only meaningful for someone who can see more than one branch.
            for row in Branch.objects.all():
                branch_revenue = payments.filter(branch=row).aggregate(
                    total=Sum("amount")
                )["total"] or 0
                branch_spend = expenses.filter(branch=row).aggregate(
                    total=Sum("amount")
                )["total"] or 0
                by_branch.append(
                    {
                        "uuid": str(row.uuid),
                        "name": row.name,
                        "revenue": branch_revenue,
                        "expenses": branch_spend,
                        "net": branch_revenue - branch_spend,
                    }
                )

        by_method = [
            {
                "name": entry["method__name"] or "غير محدد",
                "total": entry["total"],
                "count": entry["count"],
            }
            for entry in payments.values("method__name")
            .annotate(total=Sum("amount"), count=Count("id"))
            .order_by("-total")
        ]

        by_category = [
            {
                "name": entry["category__name"] or "غير محدد",
                "total": entry["total"],
                "count": entry["count"],
            }
            for entry in expenses.values("category__name")
            .annotate(total=Sum("amount"), count=Count("id"))
            .order_by("-total")
        ]

        return Response(
            {
                "from": date_from,
                "to": date_to,
                "revenue": total_revenue,
                "revenue_count": revenue["count"],
                "expenses": total_expenses,
                "expenses_count": spend["count"],
                "net": total_revenue - total_expenses,
                "by_branch": by_branch,
                "by_method": by_method,
                "by_category": by_category,
            }
        )
