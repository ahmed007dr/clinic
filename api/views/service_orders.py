"""The clinic's side of the customers' service orders (docs/16, Phase C).

    GET  /api/service-orders/                  the orders of your clinic (the Owner: every clinic), filter `?status=`, `?branch=`
    GET  /api/service-orders/<uuid>/           one order, with the doctors who could take each service
    POST /api/service-orders/<uuid>/approve/   the clinic's Admin (or the Owner) accepts it
    POST /api/service-orders/<uuid>/reject/    …or refuses it, with a reason (`{note}`)
    POST /api/service-orders/<uuid>/contacted/ customer service phoned the customer (`{note}`)
    POST /api/service-orders/<uuid>/schedule/  settle it: `{lines: [{line, doctor, scheduled_date}]}` creates the bookings

The flow the group's owner asked for: the customer sends the order; **the Admin of
the chosen clinic approves** (nobody else decides); **customer service** — the
clinic's reception — phones the customer; then the doctor and time are settled
and real bookings are made. From that point the queue, shifts, payments and the
doctor's share work exactly as for any booking.

Visible only to the front desk (Owner, Admin, Reception); a clinic sees its own
orders only, and another clinic's uuid is a 404. A doctor has no business here.
"""

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.roles import is_clinic_admin, sees_all_branches
from api.permissions import IsFrontDesk
from appointments.models import Appointment
from billing.pricing import ZERO, price_for, quantity_total, rate_for
from employees.models import Employee
from portal.models import ServiceOrder
from portal.orders import line_payload
from notifications import orders as told
from tenants.context import tenant_context

NOT_FOUND = {"detail": "غير موجود."}


def _orders_for(user):
    queryset = ServiceOrder.objects.select_related("patient", "branch", "reviewed_by", "contacted_by")
    if sees_all_branches(user):
        return queryset
    return queryset.filter(branch_id=user.branch_id) if user.branch_id else queryset.none()


def candidates(order, line):
    """Doctors who could take this service at this clinic: they work there (home
    or visiting), are under an active contract for it, and their login is not
    stopped. With what each would charge — what the desk quotes on the phone."""
    if not line.service_id:
        return []
    doctors = (
        Employee.objects.filter(employee_type__name="Doctor")
        .filter(Q(branch_id=order.branch_id) | Q(extra_branches=order.branch_id))
        .exclude(user_account__is_active=False)
        .distinct().order_by("name")
    )
    found = []
    for doctor in doctors:
        if rate_for(doctor, line.service) is None:
            continue
        price = price_for(doctor, line.service)
        found.append({"uuid": str(doctor.uuid), "name": doctor.name, "price": None if price is None else str(price)})
    return found


def payload(order, detail=False):
    lines = list(order.lines.all())
    patient = order.patient
    body = {
        "uuid": str(order.uuid),
        "serial_number": order.serial_number,
        "status": order.status,
        "status_label": order.get_status_display(),
        "branch": str(order.branch.uuid),
        "branch_name": order.branch.name,
        "patient": str(patient.uuid),
        "patient_name": patient.name,
        "patient_phone": patient.phone1 or "",
        "patient_serial": patient.serial_number,
        "notes": order.notes,
        "preferred_contact": order.preferred_contact,
        "lines": [
            {"uuid": str(line.uuid), **line_payload(line),
             "appointment": str(line.appointment.uuid) if line.appointment_id else None,
             **({"candidates": candidates(order, line)} if detail else {})}
            for line in lines
        ],
        "total": str(sum((line.price for line in lines), Decimal("0"))),
        "total_is_estimate": any(not line.price_is_final for line in lines),
        "created_at": order.created_at.isoformat(),
        "reviewed_by": order.reviewed_by.get_full_name() or order.reviewed_by.username if order.reviewed_by_id else None,
        "reviewed_at": order.reviewed_at.isoformat() if order.reviewed_at else None,
        "review_note": order.review_note,
        "contacted_by": order.contacted_by.get_full_name() or order.contacted_by.username if order.contacted_by_id else None,
        "contacted_at": order.contacted_at.isoformat() if order.contacted_at else None,
        "contact_note": order.contact_note,
    }
    return body


class ServiceOrderListView(APIView):
    permission_classes = [IsFrontDesk]

    def get(self, request):
        queryset = _orders_for(request.user).prefetch_related("lines__service", "lines__appointment")
        status = request.query_params.get("status")
        if status in {value for value, _ in ServiceOrder.Status.choices}:
            queryset = queryset.filter(status=status)
        elif status == "open":
            queryset = queryset.filter(status__in=ServiceOrder.OPEN)
        branch = request.query_params.get("branch")
        if branch and sees_all_branches(request.user):
            queryset = queryset.filter(branch__uuid=branch)
        counts = _orders_for(request.user).aggregate(
            to_approve=Count("pk", filter=Q(status=ServiceOrder.Status.SUBMITTED)),
            to_call=Count("pk", filter=Q(status__in=[ServiceOrder.Status.APPROVED, ServiceOrder.Status.CONTACTED])),
        )
        rows = [payload(order) for order in queryset[:200]]
        return Response({"counts": counts, "results": rows})


class _Order(APIView):
    permission_classes = [IsFrontDesk]

    def load(self, request, uuid):
        return get_object_or_404(_orders_for(request.user).prefetch_related("lines__service", "lines__appointment"), uuid=uuid)


class ServiceOrderDetailView(_Order):
    def get(self, request, uuid):
        return Response(payload(self.load(request, uuid), detail=True))


def _note(request, limit=300):
    return str(request.data.get("note") or "").strip()[:limit]


def _later(order, *calls):
    """Tell people once the change is committed — inside the group's context,
    which a commit hook can outlive."""

    def run():
        with tenant_context(order.tenant):
            for call in calls:
                call()

    transaction.on_commit(run)


def _move(order, status, user, **fields):
    order.status = status
    for name, value in fields.items():
        setattr(order, name, value)
    order.save()


class ServiceOrderApproveView(_Order):
    def post(self, request, uuid):
        if not is_clinic_admin(request.user):
            return Response({"detail": "الموافقة على الطلبات للأدمن فقط."}, status=403)
        order = self.load(request, uuid)
        if order.status != ServiceOrder.Status.SUBMITTED:
            return Response({"detail": "هذا الطلب ليس بانتظار الموافقة."}, status=400)
        _move(order, ServiceOrder.Status.APPROVED, request.user,
              reviewed_by=request.user, reviewed_at=timezone.now(), review_note=_note(request))
        _later(order, lambda: told.approved(order), lambda: told.approved_for_calling(order))
        return Response(payload(order, detail=True))


class ServiceOrderRejectView(_Order):
    def post(self, request, uuid):
        if not is_clinic_admin(request.user):
            return Response({"detail": "رفض الطلبات للأدمن فقط."}, status=403)
        order = self.load(request, uuid)
        if order.status not in (ServiceOrder.Status.SUBMITTED, ServiceOrder.Status.APPROVED, ServiceOrder.Status.CONTACTED):
            return Response({"detail": "لا يمكن رفض هذا الطلب الآن."}, status=400)
        note = _note(request)
        if not note:
            return Response({"note": ["اكتب سبب الرفض ليصل للعميل."]}, status=400)
        _move(order, ServiceOrder.Status.REJECTED, request.user,
              reviewed_by=request.user, reviewed_at=timezone.now(), review_note=note)
        _later(order, lambda: told.rejected(order))
        return Response(payload(order, detail=True))


class ServiceOrderContactedView(_Order):
    def post(self, request, uuid):
        order = self.load(request, uuid)
        if order.status != ServiceOrder.Status.APPROVED:
            return Response({"detail": "لا يُسجَّل الاتصال إلا بعد موافقة الأدمن."}, status=400)
        _move(order, ServiceOrder.Status.CONTACTED, request.user,
              contacted_by=request.user, contacted_at=timezone.now(), contact_note=_note(request))
        return Response(payload(order, detail=True))


class ServiceOrderScheduleView(_Order):
    """Settle the order: a doctor and a time for each service. All or nothing."""

    def post(self, request, uuid):
        order = self.load(request, uuid)
        if order.status not in (ServiceOrder.Status.APPROVED, ServiceOrder.Status.CONTACTED):
            return Response({"detail": "يُحدَّد الموعد بعد موافقة الأدمن."}, status=400)
        lines = {str(line.uuid): line for line in order.lines.all()}
        given = request.data.get("lines")
        if not isinstance(given, list) or {str(g.get("line")) for g in given if isinstance(g, dict)} != set(lines):
            return Response({"lines": ["حدد الطبيب والموعد لكل خدمة في الطلب."]}, status=400)

        plan, errors = [], {}
        for entry in given:
            line = lines[str(entry["line"])]
            doctor = Employee.objects.filter(uuid=str(entry.get("doctor") or "")).first() if entry.get("doctor") else None
            when = parse_datetime(str(entry.get("scheduled_date") or "").replace("T", " ").strip())
            if doctor is None or str(doctor.uuid) not in {c["uuid"] for c in candidates(order, line)}:
                errors[str(line.uuid)] = f"{line.service_name}: اختر طبيباً يقدّم الخدمة في هذه العيادة."
            elif when is None or when < timezone.now() - timedelta(hours=1):
                errors[str(line.uuid)] = f"{line.service_name}: اكتب موعداً صحيحاً في المستقبل."
            else:
                plan.append((line, doctor, when))
        if errors:
            return Response({"lines": errors}, status=400)

        booked = []
        with transaction.atomic():
            for line, doctor, when in plan:
                service = line.service
                unit = price_for(doctor, service) or ZERO
                quantity = line.quantity
                price = quantity_total(unit, quantity) if quantity is not None else unit
                specialization = (
                    service.specialization
                    if service.specialization_id and doctor.specializations.filter(pk=service.specialization_id).exists()
                    else None
                )
                appointment = Appointment.objects.create(
                    tenant=order.tenant, patient=order.patient, branch=order.branch, doctor=doctor, service=service,
                    specialization=specialization, status="waiting", scheduled_date=when, price=price,
                    quantity=quantity, unit_price=unit if quantity is not None else None,
                    quantity_is_estimate=bool(quantity is not None and service.doctor_sets_quantity),
                    source=Appointment.Source.PUBLIC_PORTAL, created_by=request.user,
                    notes=f"[من طلب {order.serial_number}]",
                )
                line.appointment = appointment
                line.price, line.unit_price = price, (unit if unit else line.unit_price)
                line.price_is_final = not (quantity is not None and service.doctor_sets_quantity)
                line.save(update_fields=["appointment", "price", "unit_price", "price_is_final"])
                booked.append(appointment)
            order.status = ServiceOrder.Status.SCHEDULED
            order.save(update_fields=["status", "updated_at"])
        _later(order, lambda: told.scheduled(order, booked))
        return Response(payload(order, detail=True))
