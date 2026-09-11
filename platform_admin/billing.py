"""What each owner group owes the platform — invoices, payments, balance.

The group owner's decisions (2026-09-11): monthly or yearly per group, a
negotiated price where there is one, discounts for a limited period as a
percentage and/or a fixed amount, payments by cash, bank transfer or an online
gateway, and lateness recorded by the operator rather than by a fixed rule.
"""

import calendar
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from subscriptions.entitlements import current_subscription
from tenants.context import tenant_context

from .models import CommercialTerms, Discount, LateNote, PlatformInvoice, PlatformPayment

CENT = Decimal("0.01")
ZERO = Decimal("0")
#: Days from issue to due date.
DUE_AFTER_DAYS = 7


class BillingError(ValueError):
    """The message is for the operator."""


def money(value):
    return Decimal(value or 0).quantize(CENT, rounding=ROUND_HALF_UP)


def add_months(day, months):
    month = day.month - 1 + months
    year = day.year + month // 12
    month = month % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def terms_for(customer):
    terms, _ = CommercialTerms.objects.get_or_create(customer=customer)
    return terms


def period_price(customer, terms=None):
    """(amount, description) for one billing period of this group."""
    terms = terms or terms_for(customer)
    with tenant_context(customer):
        subscription = current_subscription(customer)
    plan = subscription.plan if subscription else None
    cycle_label = terms.get_cycle_display()
    if terms.custom_price is not None:
        return money(terms.custom_price), f"اشتراك {cycle_label} — سعر متفق عليه"
    if plan is None:
        raise BillingError("لا توجد باقة لهذه المجموعة ولا سعر متفق عليه.")
    price = Decimal(plan.price)
    if terms.cycle == CommercialTerms.Cycle.YEARLY and plan.billing_period != "yearly":
        price *= 12
    elif terms.cycle == CommercialTerms.Cycle.MONTHLY and plan.billing_period == "yearly":
        price /= 12
    return money(price), f"اشتراك {cycle_label} — باقة {plan.name}"


def discount_on(customer, amount, on_day):
    """The discount for a period starting `on_day`: every active discount's
    percentage first, then every fixed amount; never below zero."""
    active = Discount.objects.filter(customer=customer, starts_on__lte=on_day, ends_on__gte=on_day)
    total = ZERO
    remaining = Decimal(amount)
    for discount in active:
        if discount.percent:
            cut = money(remaining * Decimal(discount.percent) / 100)
            total += cut
            remaining -= cut
    for discount in active:
        if discount.amount:
            cut = min(money(discount.amount), remaining)
            total += cut
            remaining -= cut
    return money(total)


def _next_number(on_day):
    prefix = f"INV-{on_day:%Y%m}-"
    last = (
        PlatformInvoice.objects.filter(number__startswith=prefix)
        .order_by("-number").values_list("number", flat=True).first()
    )
    return f"{prefix}{int(last.rsplit('-', 1)[1]) + 1 if last else 1:04d}"


@transaction.atomic
def issue_invoice(customer, actor=None, period_start=None):
    """One period's invoice, from the group's terms and discounts; advances
    the date the next one is due."""
    terms = terms_for(customer)
    start = period_start or terms.next_invoice_on or timezone.now().date()
    months = 12 if terms.cycle == CommercialTerms.Cycle.YEARLY else 1
    end = add_months(start, months) - timedelta(days=1)
    base, description = period_price(customer, terms)
    cut = discount_on(customer, base, start)
    invoice = PlatformInvoice.objects.create(
        customer=customer,
        number=_next_number(start),
        period_start=start,
        period_end=end,
        description=description,
        base_amount=base,
        discount_amount=cut,
        total=money(base - cut),
        currency=terms.currency,
        due_on=timezone.now().date() + timedelta(days=DUE_AFTER_DAYS),
        created_by=actor,
    )
    terms.next_invoice_on = end + timedelta(days=1)
    terms.save(update_fields=["next_invoice_on"])
    return invoice


def refresh_status(invoice):
    if invoice.status == PlatformInvoice.Status.VOID:
        return invoice
    paid = invoice.payments.filter(status=PlatformPayment.Status.CONFIRMED).aggregate(t=Sum("amount"))["t"] or ZERO
    invoice.status = (
        PlatformInvoice.Status.PAID if paid >= invoice.total
        else PlatformInvoice.Status.PARTIAL if paid > 0
        else PlatformInvoice.Status.OPEN
    )
    invoice.save(update_fields=["status"])
    return invoice


@transaction.atomic
def record_payment(customer, amount, method, *, actor=None, invoice=None, reference="", paid_at=None,
                   status=PlatformPayment.Status.CONFIRMED, mode="", payload=None):
    amount = money(amount)
    if amount <= 0:
        raise BillingError("المبلغ يجب أن يكون أكبر من صفر.")
    if invoice is not None and invoice.customer_id != customer.pk:
        raise BillingError("الفاتورة لا تخص هذه المجموعة.")
    payment = PlatformPayment.objects.create(
        customer=customer, invoice=invoice, amount=amount, method=method, status=status,
        reference=reference[:120], mode=mode, gateway_payload=payload or {},
        paid_at=paid_at or timezone.now(), recorded_by=actor,
    )
    if invoice is not None:
        refresh_status(invoice)
    return payment


def void_invoice(invoice, reason=""):
    invoice.status = PlatformInvoice.Status.VOID
    invoice.notes = (f"{invoice.notes} — ملغاة: {reason}" if reason else invoice.notes)[:300]
    invoice.save(update_fields=["status", "notes"])
    return invoice


def account(customer):
    """The group's balance: what was invoiced (not voided) less what was paid."""
    invoiced = PlatformInvoice.objects.filter(customer=customer).exclude(
        status=PlatformInvoice.Status.VOID
    ).aggregate(t=Sum("total"))["t"] or ZERO
    paid = PlatformPayment.objects.filter(
        customer=customer, status=PlatformPayment.Status.CONFIRMED
    ).aggregate(t=Sum("amount"))["t"] or ZERO
    overdue = PlatformInvoice.objects.filter(
        customer=customer, status__in=[PlatformInvoice.Status.OPEN, PlatformInvoice.Status.PARTIAL],
        due_on__lt=timezone.now().date(),
    ).count()
    late = LateNote.objects.filter(customer=customer, resolved_at__isnull=True).first()
    return {
        "invoiced": str(money(invoiced)),
        "paid": str(money(paid)),
        "balance": str(money(invoiced - paid)),
        "overdue_invoices": overdue,
        "late": {"note": late.note, "since": late.created_at} if late else None,
    }


def mark_late(customer, note, actor=None):
    """The operator records a group as late. A record and nothing more: the
    subscription is left as it is on purpose — `current_subscription` serves
    only "active" ones, so flipping it to past-due would silently strip the
    group's plan, which is a suspension by another name. Suspending stays an
    explicit, separate act (TenantStatusView)."""
    LateNote.objects.filter(customer=customer, resolved_at__isnull=True).update(resolved_at=timezone.now())
    return LateNote.objects.create(customer=customer, note=note[:300] or "متأخر السداد", created_by=actor)


def clear_late(customer):
    LateNote.objects.filter(customer=customer, resolved_at__isnull=True).update(resolved_at=timezone.now())
