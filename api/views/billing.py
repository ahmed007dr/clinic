"""Payments, expenses and the financial report."""

from django.db.models import Count, Sum
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from api.permissions import IsClinicMember, ReadOnlyForNonAdmin, is_clinic_admin
from api.serializers.billing import (
    ExpenseCategorySerializer,
    ExpenseSerializer,
    PaymentMethodSerializer,
    PaymentSerializer,
)
from api.viewsets import ClinicViewSet
from billing.models import Expense, ExpenseCategory, Payment, PaymentMethod
from branches.models import Branch


def _date_range(params):
    return params.get("from"), params.get("to")


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


class PaymentViewSet(ClinicViewSet):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    permission_classes = [IsClinicMember]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["receipt_number", "patient__name", "appointment__serial_number"]
    ordering_fields = ["date", "amount", "receipt_number"]
    ordering = ["-date"]

    def filter_tenant_queryset(self, queryset):
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


class ExpenseViewSet(ClinicViewSet):
    queryset = Expense.objects.all()
    serializer_class = ExpenseSerializer
    permission_classes = [IsClinicMember]
    created_by_field = "created_by"
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["notes", "category__name", "employee__name"]
    ordering_fields = ["date", "amount"]
    ordering = ["-date"]

    def filter_tenant_queryset(self, queryset):
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

    A viewset with a single list action rather than a plain APIView so it
    inherits the branch scoping instead of restating it — the numbers a
    receptionist sees must cover their branch only, and a report that quietly
    totals the whole clinic is worse than no report.
    """

    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    permission_classes = [IsClinicMember]
    http_method_names = ["get", "head", "options"]
    pagination_class = None

    def list(self, request):
        params = request.query_params
        date_from, date_to = _date_range(params)
        branch = params.get("branch")

        from api.permissions import scope_queryset_to_user

        payments = scope_queryset_to_user(Payment.objects.all(), request.user)
        expenses = scope_queryset_to_user(Expense.objects.all(), request.user)

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
        if is_clinic_admin(request.user):
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
