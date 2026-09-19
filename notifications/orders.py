"""Telling people about a service order (docs/16).

The customer is told by e-mail (through `notifications.maillog.deliver`, so every
message is in the clinic's e-mail log) at each step: the order was received and
now waits for the clinic's approval, the clinic approved or refused it, and the
time was settled. The clinic's front desk is told in-app (`Notification`) when an
order arrives or is withdrawn — the Admin who must decide, and customer service
who will phone.

Callers use `transaction.on_commit`; nothing here raises — a dead mail server
never stops an order.
"""

import logging
from decimal import Decimal

from .booking import staff_of
from .maillog import deliver
from .models import Notification

logger = logging.getLogger(__name__)


def _money(value):
    return f"{Decimal(value or 0):.2f}"


def line_text(line):
    """One service of an order, as the customer reads it."""
    text = f"• {line.service_name}"
    if line.quantity is not None:
        unit = f" {line.quantity_unit}" if line.quantity_unit else ""
        text += f" × {line.quantity.normalize():f}{unit}"
    if line.unit_price is None:
        return text + " — السعر بعد تقييم الطبيب"
    prefix = "" if line.price_is_final else "≈ "
    text = f"{text} — {prefix}{_money(line.price)} جنيه"
    if line.preferred_at:
        text += f" — الموعد المفضل {line.preferred_at:%Y-%m-%d %H:%M}"
    return text


def order_block(order):
    """A whole order: its number, the clinic to reach, and its lines."""
    branch = order.branch
    lines = [f"طلب رقم {order.serial_number} — {branch.name}"]
    if branch.phone:
        lines.append(f"للتواصل: {branch.phone}")
    lines.extend(line_text(line) for line in order.lines.all())
    total = sum((line.price for line in order.lines.all()), Decimal("0"))
    if total and any(not line.price_is_final for line in order.lines.all()):
        lines.append(f"الإجمالي التقديري: {_money(total)} جنيه — يتحدد السعر النهائي عند الحجز مع الطبيب")
    elif total:
        lines.append(f"الإجمالي: {_money(total)} جنيه")
    return lines


def can_email(patient):
    return bool((patient.email or "").strip())


def _email(kind, patient, branch, subject, intro, blocks, outro=()):
    from platform_admin.mailer import sender_for

    if not can_email(patient):
        return False
    tenant = patient.tenant
    body_lines = [f"مرحباً {patient.name}،", "", intro, ""]
    for block in blocks:
        body_lines.extend([*block, ""])
    body_lines.extend(outro)
    try:
        connection, sender = sender_for(branch=branch, customer=tenant)
        return deliver(
            kind=kind, tenant=tenant, branch=branch, to=patient.email.strip(),
            subject=f"{subject} — {tenant.name}", body="\n".join(body_lines).strip(),
            connection=connection, sender=sender,
        )
    except Exception:  # noqa: BLE001 — never stop an order over an e-mail
        logger.exception("Could not send a %s e-mail", kind)
        return False


# ------------------------------------------------------------ to the customer


def received(orders):
    """The customer sent one or more orders: one e-mail with all of them."""
    orders = list(orders)
    if not orders:
        return False
    return _email(
        "order_received", orders[0].patient, orders[0].branch, "استلمنا طلبك",
        "استلمنا طلبك، وهو الآن بانتظار موافقة العيادة. بعد الموافقة تتصل بك خدمة العملاء لتحديد الطبيب والموعد.",
        [order_block(order) for order in orders],
        ["ستصلك رسالة أخرى عند رد العيادة. تتابع طلباتك أيضاً من «طلباتي» في حسابك.",
         "الدفع عند الوصول للعيادة. هذه رسالة آلية؛ لا حاجة للرد عليها."],
    )


def approved(order):
    return _email(
        "order_approved", order.patient, order.branch, "وافقت العيادة على طلبك",
        "وافقت العيادة على طلبك. ستتصل بك خدمة العملاء قريباً لتحديد الطبيب والموعد.",
        [order_block(order)],
    )


def rejected(order):
    note = [f"السبب: {order.review_note}"] if order.review_note else []
    return _email(
        "order_rejected", order.patient, order.branch, "تعذّر تنفيذ طلبك",
        "نأسف، لم تتمكن العيادة من قبول هذا الطلب. للاستفسار تواصل مع العيادة.",
        [order_block(order), note] if note else [order_block(order)],
    )


def scheduled(order, appointments):
    """The time was settled: what was booked, with whom, when."""
    blocks = [order_block(order)]
    booked = ["المواعيد:"]
    for appointment in appointments:
        doctor = f" مع د. {appointment.doctor.name}" if appointment.doctor_id else ""
        booked.append(f"• {appointment.service.name}{doctor} — {appointment.scheduled_date:%Y-%m-%d — %H:%M}")
    if order.branch.address:
        booked.append(f"العنوان: {order.branch.address}")
    return _email(
        "order_scheduled", order.patient, order.branch, "تم تحديد موعدك",
        "تم تحديد موعد طلبك.", [*blocks, booked],
        ["الدفع عند الوصول للعيادة. إن أردت تغيير الموعد أو إلغاءه فمن حسابك أو بالاتصال بالعيادة."],
    )


# ------------------------------------------------------------ to the staff


def tell_staff(order, title, message):
    """An in-app notice for the clinic's Admin and reception. Never raises."""
    try:
        users = list(staff_of(order.branch_id))
        for user in users:
            Notification.objects.create(tenant=order.tenant, user=user, type="appointment", title=title, message=message)
        return len(users)
    except Exception:  # noqa: BLE001
        logger.exception("Could not notify the clinic's staff about an order")
        return 0


def arrived(order):
    what = "، ".join(line.service_name for line in order.lines.all())
    return tell_staff(
        order, "طلب خدمات جديد من الموقع",
        f"{order.patient.name} — {what} (طلب {order.serial_number}). يحتاج موافقة الأدمن ثم اتصال خدمة العملاء.",
    )


def withdrawn(order):
    return tell_staff(
        order, "ألغى العميل طلبه",
        f"{order.patient.name} ألغى الطلب {order.serial_number} من الموقع.",
    )


def approved_for_calling(order):
    """After the Admin's approval, customer service is told there is a call to make."""
    return tell_staff(
        order, "طلب بانتظار اتصال خدمة العملاء",
        f"وافقت العيادة على الطلب {order.serial_number} ({order.patient.name}). اتصل بالعميل لتحديد الطبيب والموعد.",
    )
