"""Discount coupons: management issues them, the front desk applies them.

    GET  /api/coupons/                 ?patient=<uuid>&available=1 — for the booking form
    POST /api/coupons/                 Admin / Owner only: a patient, an amount, a service or a specialty
    POST /api/coupons/<uuid>/void/     Admin / Owner only: cancel one that is not yet spent

A coupon is never edited (issue another) and never deleted: who gave whom what
discount, and when, is the record.
"""

from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from api.permissions import IsFrontDesk, ReadOnlyForNonAdmin
from api.relations import TenantScopedRelatedField
from api.serializers.common import ActiveChoicesMixin, ClinicSerializer
from api.viewsets import ClinicViewSet
from billing.models import DiscountCoupon
from employees.models import Specialization
from patients.models import Patient
from services.models import Service


class CouponSerializer(ActiveChoicesMixin, ClinicSerializer):
    patient = TenantScopedRelatedField(model=Patient, branch_field="branch")
    service = TenantScopedRelatedField(model=Service, required=False, allow_null=True)
    specialization = TenantScopedRelatedField(model=Specialization, required=False, allow_null=True)

    patient_name = serializers.CharField(source="patient.name", read_only=True)
    service_name = serializers.CharField(source="service.name", read_only=True, default=None)
    specialization_name = serializers.CharField(source="specialization.name", read_only=True, default=None)
    created_by_name = serializers.SerializerMethodField()
    status = serializers.CharField(read_only=True)

    class Meta:
        model = DiscountCoupon
        fields = [
            "uuid", "patient", "patient_name", "amount",
            "service", "service_name", "specialization", "specialization_name",
            "expires_on", "notes", "status", "created_at", "created_by_name",
            "used_at", "voided_at",
        ]
        read_only_fields = ["used_at", "voided_at"]

    def get_created_by_name(self, coupon):
        from accounts.roles import display_name

        return display_name(coupon.created_by) if coupon.created_by else None

    def validate(self, attrs):
        if attrs.get("service") is None and attrs.get("specialization") is None:
            raise serializers.ValidationError(
                {"service": "حدد الخدمة (مثل الكشف العادي) أو التخصص الذي ينطبق عليه الخصم."}
            )
        expires_on = attrs.get("expires_on")
        if expires_on and expires_on < timezone.now().date():
            raise serializers.ValidationError({"expires_on": "تاريخ الانتهاء في الماضي."})
        return attrs


class CouponViewSet(ClinicViewSet):
    queryset = DiscountCoupon.objects.all()
    serializer_class = CouponSerializer
    # The desk reads (to apply one); only management issues or cancels.
    permission_classes = [IsFrontDesk, ReadOnlyForNonAdmin]
    # A coupon follows its patient's clinic.
    branch_field = "patient__branch"
    created_by_field = "created_by"
    http_method_names = ["get", "post", "head", "options"]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["patient__name", "patient__phone1", "service__name", "specialization__name"]
    ordering = ["-created_at"]

    def filter_tenant_queryset(self, queryset):
        queryset = queryset.select_related("patient", "service", "specialization", "created_by")
        params = self.request.query_params
        if params.get("patient"):
            queryset = queryset.filter(patient__uuid=params["patient"])
        if params.get("available") == "1":
            today = timezone.now().date()
            queryset = queryset.filter(voided_at__isnull=True, used_at__isnull=True).exclude(
                expires_on__lt=today
            )
        return queryset

    @action(detail=True, methods=["post"], url_path="void")
    def void(self, request, uuid=None):
        coupon = self.get_object()
        if coupon.used_at:
            raise ValidationError({"detail": "لا يمكن إلغاء كوبون استُخدم بالفعل."})
        if coupon.voided_at is None:
            coupon.voided_at = timezone.now()
            coupon.save(update_fields=["voided_at"])
        return Response(self.get_serializer(coupon).data)
