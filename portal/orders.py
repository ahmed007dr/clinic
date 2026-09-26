"""«طلباتي» — the customer's service orders (docs/16, Phase B).

    GET  orders/                  the signed-in customer's orders, newest first
    POST orders/                  send the basket: `{items: [{service, branch, quantity?}], notes, preferred_contact}`
    GET  orders/<uuid>/           one order
    POST orders/<uuid>/cancel/    withdraw it while the clinic has not finished with it

The basket lives in the customer's browser until it is sent; sending needs a
signed-in customer (an account proved by an e-mail code). One order is made
**per clinic**, each decided by its own clinic. Nothing the browser says is
trusted: every item is re-checked against the catalogue (`services.catalog`),
the quantity against the service's limits (`billing.pricing`), and the price is
worked out here — the lowest a doctor of that clinic charges for it, marked
«تقديري» when it depends on which doctor, on the quantity the doctor sets, or on
an evaluation. An order holds no doctor's time; nothing enters a schedule until
the clinic settles it.
"""

import uuid as uuid_module
from collections import OrderedDict
from decimal import Decimal, InvalidOperation

from django.db import transaction
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle

from billing.pricing import quantity_problem, quantity_total
from branches.models import Branch
from services.catalog import offerings
from services.models import Service
from tenants.context import tenant_context

from .models import ServiceOrder, ServiceOrderLine
from .views import PortalView

MAX_LINES = 10
MAX_OPEN_ORDERS = 3
NOT_ORDERABLE = "هذه الخدمة غير متاحة للطلب في العيادة المختارة."
NOT_FOUND = {"detail": "غير موجود."}


class OrderThrottle(SimpleRateThrottle):
    """Sending and withdrawing orders, per customer — so send/cancel/send cannot
    be looped to flood a clinic's desk."""

    scope = "portal_order"

    def get_cache_key(self, request, view):
        patient = getattr(request.user, "patient", None)
        return self.cache_format % {"scope": self.scope, "ident": getattr(patient, "pk", None) or self.get_ident(request)}


def _uuid(value):
    try:
        return uuid_module.UUID(str(value or ""))
    except ValueError:
        return None


def _money(value):
    return None if value is None else str(value)


def line_payload(line):
    return {
        "service": str(line.service.uuid) if line.service_id else None,
        "service_name": line.service_name,
        "quantity": _money(line.quantity),
        "quantity_unit": line.quantity_unit,
        "unit_price": _money(line.unit_price),
        "price": _money(line.price),
        "price_is_final": line.price_is_final,
        "preferred_doctor": line.preferred_doctor.name if line.preferred_doctor_id else None,
        "preferred_at": line.preferred_at.isoformat() if line.preferred_at else None,
    }


def order_payload(order):
    lines = list(order.lines.all())
    total = sum((line.price for line in lines), Decimal("0"))
    appointments = [
        {
            "uuid": str(line.appointment.uuid), "service_name": line.service_name,
            "doctor_name": line.appointment.doctor.name if line.appointment.doctor_id else None,
            "scheduled_date": line.appointment.scheduled_date.isoformat(),
        }
        for line in lines if line.appointment_id
    ]
    return {
        "uuid": str(order.uuid),
        "serial_number": order.serial_number,
        "status": order.status,
        "status_label": order.get_status_display(),
        "is_open": order.is_open,
        "branch": {
            "uuid": str(order.branch.uuid), "name": order.branch.name,
            "phone": order.branch.phone or "", "address": order.branch.address or "",
        },
        "lines": [line_payload(line) for line in lines],
        "total": str(total),
        "total_is_estimate": any(not line.price_is_final for line in lines),
        "notes": order.notes,
        "preferred_contact": order.preferred_contact,
        # The clinic's word, once it has given it.
        "review_note": order.review_note,
        "appointments": appointments,
        "payment_preference": order.payment_preference,
        "payment_preference_label": order.get_payment_preference_display(),
        "created_at": order.created_at.isoformat(),
    }


def price_line(service, branch, quantity, doctor=None):
    """`(unit_price, price, price_is_final)` for one service at one clinic, or
    None when no doctor there can be booked for it. The unit price is the lowest
    a doctor charges; it is final only when every doctor charges the same, the
    service is priced as one fixed thing, and the doctor does not set its quantity."""
    found = offerings(service=service, branch=branch, doctor=doctor)
    if not found:
        return None
    prices = [offer.price for offer in found if offer.price is not None]
    if not prices:  # priced after the doctor's evaluation
        return None, Decimal("0"), False
    unit = min(prices)
    total = quantity_total(unit, quantity) if quantity is not None else unit
    final = (
        len(set(prices)) == 1
        and service.price_display == Service.PriceDisplay.FIXED
        and not (service.requires_quantity and service.doctor_sets_quantity)
    )
    return unit, total, final


def _preference(service, branch, entry):
    """`(doctor, time, problem)` from an item's optional `doctor` and `slot`.

    A time must be one the availability engine really offers (`is_offered`) — with
    the doctor asked for, else with any doctor of that clinic who has it, and that
    doctor is then the preferred one. It holds nothing: two customers may prefer
    the same time, and the clinic settles which one gets it. `problem` is
    `(message, status)`."""
    from appointments.availability import is_offered

    from .booking import TAKEN, _slot

    doctor_uuid = _uuid(entry.get("doctor")) if entry.get("doctor") else None
    when = _slot(entry.get("slot")) if entry.get("slot") else None
    if entry.get("slot") and when is None:
        return None, None, ("اختر موعداً من الأوقات المتاحة.", 400)
    offers = offerings(service=service, branch=branch)
    if doctor_uuid:
        offers = [o for o in offers if o.doctor.uuid == doctor_uuid]
        if not offers:
            return None, None, (NOT_ORDERABLE, 400)
    if when is None:
        return (offers[0].doctor if doctor_uuid else None), None, None
    for offer in offers:
        if is_offered(offer, when):
            return offer.doctor, when, None
    return None, None, (TAKEN, 409)


def clean_items(tenant, patient, raw):
    """`(items, errors[, status])`: each item is
    `(service, branch, quantity, unit, price, final, preferred doctor, preferred time)`."""
    if not isinstance(raw, list) or not raw:
        return None, {"items": ["أضف خدمة واحدة على الأقل إلى طلبك."]}
    if len(raw) > MAX_LINES:
        return None, {"items": [f"الحد الأقصى {MAX_LINES} خدمات في الطلب الواحد."]}
    items, seen = [], set()
    for index, entry in enumerate(raw):
        entry = entry if isinstance(entry, dict) else {}
        service = Service.objects.filter(uuid=_uuid(entry.get("service")), is_active=True).first() if _uuid(entry.get("service")) else None
        branch = (
            Branch.objects.filter(uuid=_uuid(entry.get("branch")), is_active=True, about_visible=True).first()
            if _uuid(entry.get("branch")) else None
        )
        if service is None or branch is None:
            return None, {"items": [f"الخدمة رقم {index + 1}: {NOT_ORDERABLE}"]}
        if (service.pk, branch.pk) in seen:
            return None, {"items": [f"«{service.name}» مكررة في نفس العيادة. غيّر الكمية بدل تكرارها."]}
        seen.add((service.pk, branch.pk))

        quantity = None
        if service.requires_quantity:
            try:
                quantity = Decimal(str(entry.get("quantity"))) if entry.get("quantity") not in (None, "") else None
            except InvalidOperation:
                quantity = None
            if quantity is None and service.doctor_sets_quantity:
                quantity = service.min_quantity  # an estimate; the doctor sets the real one
            problem = quantity_problem(service, quantity)
            if problem:
                return None, {"items": [f"{service.name}: {problem}"]}
            quantity = quantity.quantize(Decimal("0.01"))

        if patient.branch_id and patient.branch_id != branch.pk and not tenant.portal_allow_other_branches:
            return None, {"items": [f"{service.name}: الطلب عبر الموقع متاح في عيادتك فقط."]}
        doctor, when, problem = _preference(service, branch, entry)
        if problem:
            return None, {"items": [f"{service.name}: {problem[0]}"]}, problem[1]
        priced = price_line(service, branch, quantity, doctor)
        if priced is None:
            return None, {"items": [f"{service.name}: {NOT_ORDERABLE}"]}
        unit, price, final = priced
        items.append((service, branch, quantity, unit, price, final, doctor, when))
    return items, None


class OrdersView(PortalView):
    throttle_classes = [OrderThrottle]

    def get_throttles(self):
        # Only sending is limited; reading one's own orders is not.
        return super().get_throttles() if self.request.method == "POST" else []

    def get(self, request, slug):
        orders = (
            ServiceOrder.objects.filter(patient=self.patient)
            .select_related("branch").prefetch_related("lines__service", "lines__preferred_doctor", "lines__appointment__doctor")
        )
        return Response([order_payload(order) for order in orders[:100]])

    def post(self, request, slug):
        tenant, patient, data = self.tenant, self.patient, request.data
        cleaned = clean_items(tenant, patient, data.get("items"))
        items, errors = cleaned[0], cleaned[1]
        if errors:
            return Response(errors, status=cleaned[2] if len(cleaned) > 2 else 400)
        notes = str(data.get("notes") or "").strip()[:1000]
        contact = str(data.get("preferred_contact") or "").strip()[:100]
        preference = str(data.get("payment_preference") or ServiceOrder.Payment.MANUAL)
        if preference not in ServiceOrder.Payment.values:
            return Response({"payment_preference": ["اختر طريقة الدفع."]}, status=400)

        by_branch = OrderedDict()
        for item in items:
            by_branch.setdefault(item[1], []).append(item)
        open_now = ServiceOrder.objects.filter(patient=patient, status__in=ServiceOrder.OPEN).count()
        if open_now + len(by_branch) > MAX_OPEN_ORDERS:
            return Response(
                {"detail": f"لا يمكن أن يزيد عدد طلباتك المفتوحة عن {MAX_OPEN_ORDERS}. "
                           "انتظر رد العيادة على طلباتك أو ألغِ أحدها."},
                status=400,
            )

        with transaction.atomic():
            orders = []
            for branch, rows in by_branch.items():
                order = ServiceOrder.objects.create(
                    tenant=tenant, patient=patient, branch=branch, notes=notes, preferred_contact=contact,
                    payment_preference=preference,
                )
                for service, _, quantity, unit, price, final, doctor, when in rows:
                    ServiceOrderLine.objects.create(
                        tenant=tenant, order=order, service=service, service_name=service.name,
                        quantity=quantity, quantity_unit=service.quantity_unit if quantity is not None else "",
                        unit_price=unit, price=price, price_is_final=final,
                        preferred_doctor=doctor, preferred_at=when,
                    )
                orders.append(order)

        from notifications import orders as told

        def announce():
            # Explicitly in the group's context: an on-commit hook can run after the
            # request's own context has closed.
            with tenant_context(tenant):
                fresh = list(
                    ServiceOrder.objects.filter(pk__in=[o.pk for o in orders])
                    .select_related("branch", "patient").prefetch_related("lines")
                )
                told.received(fresh)
                for order in fresh:
                    told.arrived(order)

        transaction.on_commit(announce)
        fresh = (
            ServiceOrder.objects.filter(pk__in=[o.pk for o in orders])
            .select_related("branch").prefetch_related("lines__service", "lines__preferred_doctor", "lines__appointment__doctor")
        )
        return Response([order_payload(order) for order in fresh], status=201)


class _MyOrder(PortalView):
    def order(self, uuid):
        return (
            ServiceOrder.objects.filter(patient=self.patient, uuid=uuid)
            .select_related("branch").prefetch_related("lines__service", "lines__preferred_doctor", "lines__appointment__doctor").first()
        )


class OrderDetailView(_MyOrder):
    def get(self, request, slug, uuid):
        order = self.order(uuid)
        return Response(order_payload(order)) if order else Response(NOT_FOUND, status=404)


class OrderCancelView(_MyOrder):
    throttle_classes = [OrderThrottle]

    def post(self, request, slug, uuid):
        order = self.order(uuid)
        if order is None:
            return Response(NOT_FOUND, status=404)
        if not order.is_open:
            return Response({"detail": "لا يمكن إلغاء هذا الطلب الآن."}, status=400)
        order.status = ServiceOrder.Status.CANCELLED
        order.save(update_fields=["status", "updated_at"])
        from notifications import orders as told

        transaction.on_commit(lambda: told.withdrawn(order))
        return Response(order_payload(order))
