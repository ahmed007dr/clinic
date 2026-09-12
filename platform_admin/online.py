"""Paying a platform invoice online, end to end.

`start` opens a pending payment and hands back the gateway's page; the
gateway's callback reaches `confirm`, which asks the adapter to verify it
(platform_admin/gateways.py) and only then marks the payment confirmed and the
invoice paid. Subscriptions are collected with the **platform's** own gateway
keys (vault scope "platform").
"""

import secrets

from django.db import transaction

from . import billing, vault
from .gateways import GatewayError, adapter, reference_in
from .models import PlatformInvoice, PlatformPayment

METHODS = {"paymob", "fawry", "vodafone_cash"}


def start(invoice, method, *, payer, return_url, actor=None):
    if method not in METHODS:
        raise GatewayError("اختر طريقة دفع إلكتروني.")
    if invoice.status in (PlatformInvoice.Status.PAID, PlatformInvoice.Status.VOID):
        raise GatewayError("لا يوجد مبلغ مستحق على هذه الفاتورة.")
    # The platform's own keys only: subscriptions are paid to the platform.
    found = vault.resolve(method)
    if found is None:
        raise GatewayError("لم تُضبط مفاتيح بوابة الدفع هذه بعد.")
    config, mode, credential = found
    remaining = invoice.total - sum(
        p.amount for p in invoice.payments.filter(status=PlatformPayment.Status.CONFIRMED)
    )
    reference = f"PP-{invoice.pk}-{secrets.token_hex(4)}"
    payment = billing.record_payment(
        invoice.customer, remaining, method, actor=actor, invoice=invoice, reference=reference,
        status=PlatformPayment.Status.PENDING, mode=mode, payload={"credential": credential.pk},
    )
    gateway = adapter(method)
    kwargs = {"amount": remaining, "reference": reference, "payer": payer}
    if method == "fawry":
        kwargs.update(mode=mode, return_url=return_url)
    try:
        result = gateway.start(config, **kwargs)
    except GatewayError:
        payment.status = PlatformPayment.Status.FAILED
        payment.save(update_fields=["status"])
        raise
    return {"redirect_url": result["redirect_url"], "reference": reference, "mode": mode}


@transaction.atomic
def confirm(method, data):
    """Returns the payment, confirmed or failed; raises GatewayError when the
    callback cannot be trusted (bad signature, unknown payment, wrong amount)."""
    gateway = adapter(method)
    reference_hint = (
        data.get("merchantRefNumber") or data.get("merchantRefNum")
        or data.get("merchant_order_id") or (data.get("obj") or {}).get("order", {}).get("merchant_order_id", "")
    )
    candidates = PlatformPayment.objects.select_for_update().filter(method=method, reference=reference_hint) \
        if reference_hint else PlatformPayment.objects.none()
    payment = candidates.first()
    if payment is None:
        raise GatewayError("عملية دفع غير معروفة.")
    if payment.status == PlatformPayment.Status.CONFIRMED:
        return payment  # a repeated callback changes nothing
    credential = vault.IntegrationCredential.objects.get(pk=payment.gateway_payload.get("credential"))
    config = vault.config_of(credential, payment.mode)
    extra = {"mode": payment.mode} if method == "fawry" else {}
    reference, paid, gateway_id = gateway.confirm(config, data, expected_amount=payment.amount, **extra)
    if reference != payment.reference:
        raise GatewayError("مرجع الدفع لا يطابق.")
    payment.status = PlatformPayment.Status.CONFIRMED if paid else PlatformPayment.Status.FAILED
    payment.gateway_payload = {**payment.gateway_payload, "gateway_id": gateway_id}
    payment.save(update_fields=["status", "gateway_payload"])
    if payment.invoice_id:
        billing.refresh_status(payment.invoice)
    return payment
