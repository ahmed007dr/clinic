"""Appointments — the booking, not the encounter.

An Appointment records that someone was *scheduled*. What actually happened is
a `medical.Visit`, and the two are separate on purpose: walk-ins have no
appointment, and a booking nobody attended produces no visit.
"""

from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from api.relations import TenantScopedRelatedField
from appointments.models import Appointment
from billing.collect import (
    PaymentRefused,
    PaymentRequired,
    amount_paid,
    coupon_problem,
    record_payment,
    require_paid,
    spend_coupon,
)
from billing.models import DiscountCoupon, PaymentMethod
from billing.pricing import enforce_attrs
from billing.shifts import ShiftError
from branches.models import Branch
from employees.models import Employee, Specialization
from patients.models import Patient
from services.models import Service

from .common import ActiveChoicesMixin, ClinicSerializer


class AppointmentSerializer(ActiveChoicesMixin, ClinicSerializer):
    # Branch-scoped: a receptionist who cannot see a patient must not be able
    # to book for them by pasting a UUID. See api/relations.py.
    patient = TenantScopedRelatedField(model=Patient, branch_field="branch")
    doctor = TenantScopedRelatedField(
        model=Employee, required=False, allow_null=True
    )
    specialization = TenantScopedRelatedField(
        model=Specialization, required=False, allow_null=True
    )
    service = TenantScopedRelatedField(
        model=Service, required=False, allow_null=True
    )
    branch = TenantScopedRelatedField(model=Branch, required=False, allow_null=True)
    # A discount coupon the patient holds; only applied when booking. The
    # discount it gives is the server's to work out (`discount` is read-only).
    coupon = TenantScopedRelatedField(model=DiscountCoupon, required=False, allow_null=True)
    # Payment taken with the booking, in the same step: how much, and how.
    paid_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, write_only=True, min_value=Decimal("0")
    )
    payment_method = TenantScopedRelatedField(
        model=PaymentMethod, required=False, allow_null=True, write_only=True
    )

    patient_name = serializers.CharField(source="patient.name", read_only=True)
    patient_phone = serializers.CharField(
        source="patient.phone1", read_only=True, default=None
    )
    doctor_name = serializers.CharField(
        source="doctor.name", read_only=True, default=None
    )
    service_name = serializers.CharField(
        source="service.name", read_only=True, default=None
    )
    branch_name = serializers.CharField(
        source="branch.name", read_only=True, default=None
    )
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    # From the visit this booking opened, if the patient has gone in: the
    # front desk books the next appointment from it (medical/checkin.py).
    follow_up_date = serializers.SerializerMethodField()
    has_visit = serializers.SerializerMethodField()
    # Paid, part-paid or not — for the front desk to check in a booking paid
    # in advance. Null for a doctor, who sees no money but their own share.
    paid_total = serializers.SerializerMethodField()
    payment_status = serializers.SerializerMethodField()
    amount_due = serializers.SerializerMethodField()
    net_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    # The receipt of the payment taken with this booking, on the response that
    # creates it — so it can be printed straight away.
    receipt_uuid = serializers.SerializerMethodField()
    # Only the queue endpoint sets it (api/views/appointments.py `waiting`):
    # how many are before this booking for its doctor. Null everywhere else.
    ahead_count = serializers.SerializerMethodField()

    class Meta:
        model = Appointment
        fields = [
            "uuid", "serial_number",
            "patient", "patient_name", "patient_phone",
            "doctor", "doctor_name",
            "specialization",
            "service", "service_name",
            "branch", "branch_name",
            "status", "status_label",
            "scheduled_date", "price", "discount", "net_price", "notes", "created_at",
            "coupon", "paid_amount", "payment_method",
            "follow_up_date", "has_visit",
            "paid_total", "payment_status", "amount_due", "receipt_uuid",
            "ahead_count",
        ]
        read_only_fields = ["discount"]

    def _paid(self, appointment):
        from accounts.roles import is_front_desk

        if not is_front_desk(self.request_user):
            return None
        # `payments` is prefetched; voided ones are not in it (billing.models).
        return sum((payment.amount for payment in appointment.payments.all()), 0)

    def get_paid_total(self, appointment):
        paid = self._paid(appointment)
        return None if paid is None else f"{paid:.2f}"

    def get_payment_status(self, appointment):
        paid = self._paid(appointment)
        if paid is None:
            return None
        if paid <= 0:
            return "unpaid"
        return "paid" if paid >= appointment.net_price else "partial"

    def get_amount_due(self, appointment):
        paid = self._paid(appointment)
        if paid is None:
            return None
        return f"{max(appointment.net_price - paid, 0):.2f}"

    def get_ahead_count(self, appointment):
        return getattr(appointment, "ahead_count", None)

    def get_receipt_uuid(self, appointment):
        receipt = getattr(appointment, "_new_receipt", None)
        return str(receipt.uuid) if receipt is not None else None

    def _visit(self, appointment):
        # `visits` is prefetched by the viewset; a list, not a query per row.
        visits = list(appointment.visits.all())
        return visits[0] if visits else None

    def get_follow_up_date(self, appointment):
        visit = self._visit(appointment)
        return visit.follow_up_date if visit else None

    def get_has_visit(self, appointment):
        return self._visit(appointment) is not None

    def validate(self, attrs):
        attrs = super().validate(attrs)
        status = attrs.get("status", getattr(self.instance, "status", None))
        doctor = attrs.get("doctor", getattr(self.instance, "doctor", None))
        if status == "entered" and doctor is None:
            raise serializers.ValidationError(
                {"doctor": "حدد الطبيب قبل تسجيل دخول المريض."}
            )
        if self.instance is None and attrs.get("branch") is None:
            # A booking with no clinic is one nobody below the Owner can see
            # again — not even the receptionist who just made it.
            from accounts.roles import current_branch_id

            patient = attrs.get("patient")
            branch_id = getattr(patient, "branch_id", None) or current_branch_id(self.request_user)
            if branch_id:
                attrs["branch"] = Branch.objects.filter(pk=branch_id).first()
        # The price is the doctor's contract price; only management sets
        # another one (billing.pricing).
        attrs = enforce_attrs(attrs, self.request_user, self.instance, price_field="price")
        self._validate_money(attrs, status)
        return attrs

    def _validate_money(self, attrs, status):
        """Coupon, payment taken now, and the "paid in full to go in" rule."""
        from accounts.roles import is_front_desk

        creating = self.instance is None
        price = attrs.get("price", getattr(self.instance, "price", None)) or Decimal("0")
        paid_now = attrs.get("paid_amount")

        # A coupon is applied when booking, never swapped afterwards.
        coupon = attrs.get("coupon")
        if not creating:
            attrs.pop("coupon", None)
            coupon = None
        discount = getattr(self.instance, "discount", None) or Decimal("0")
        if coupon is not None:
            service = attrs.get("service")
            problem = coupon_problem(
                coupon,
                attrs.get("patient"),
                service,
                attrs.get("specialization") or getattr(service, "specialization", None),
            )
            if problem:
                raise serializers.ValidationError({"coupon": problem})
            discount = min(coupon.amount, price)
            attrs["discount"] = discount

        net = max(price - discount, Decimal("0"))

        if paid_now:
            if not is_front_desk(self.request_user):
                raise serializers.ValidationError({"paid_amount": "تسجيل الدفعات للاستقبال والإدارة فقط."})
            if not creating:
                raise serializers.ValidationError({"paid_amount": "الدفعات على حجز قائم تُسجَّل من شاشة الدفعات."})
            if paid_now > net:
                raise serializers.ValidationError(
                    {"paid_amount": f"المبلغ أكبر من سعر الحجز بعد الخصم ({net:.2f})."}
                )
            if attrs.get("payment_method") is None:
                raise serializers.ValidationError({"payment_method": "اختر طريقة الدفع."})

        # Going in to the doctor needs the booking paid in full.
        if status == "entered" and (creating or self.instance.status != "entered"):
            already = Decimal("0") if creating else amount_paid(self.instance)
            try:
                require_paid(net - already - (paid_now or Decimal("0")))
            except PaymentRequired as required:
                raise serializers.ValidationError({"status": str(required)})

    @transaction.atomic
    def create(self, validated_data):
        paid_now = validated_data.pop("paid_amount", None)
        method = validated_data.pop("payment_method", None)
        coupon = validated_data.get("coupon")
        try:
            if coupon is not None:
                spend_coupon(coupon)
            appointment = super().create(validated_data)
            if paid_now:
                appointment._new_receipt = record_payment(
                    self.request_user, appointment, paid_now, method
                )
        except (PaymentRefused, ShiftError) as refused:
            # Nothing of the booking is kept: transaction.atomic rolls it all
            # back, the coupon included.
            raise serializers.ValidationError({"detail": str(refused)})
        return appointment

    def update(self, instance, validated_data):
        validated_data.pop("paid_amount", None)
        validated_data.pop("payment_method", None)
        return super().update(instance, validated_data)

    def validate_doctor(self, doctor):
        """Only staff typed as Doctor may hold an appointment.

        The model expresses this with `limit_choices_to`, which constrains the
        admin and ModelForm dropdowns and nothing else — a direct API write
        would sail past it and book a patient with the cleaner.
        """
        if doctor is None:
            return doctor
        type_name = getattr(doctor.employee_type, "name", None)
        if type_name != "Doctor":
            raise serializers.ValidationError(
                "لا يمكن حجز موعد إلا مع طبيب."
            )
        changed = self.instance is None or self.instance.doctor_id != doctor.pk
        account = getattr(doctor, "user_account", None)
        if changed and account is not None and not account.is_active:
            raise serializers.ValidationError("حساب هذا الطبيب موقوف.")
        return doctor
