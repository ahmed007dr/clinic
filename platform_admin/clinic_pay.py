"""A patient paying their clinic online — with the clinic's own keys.

The developer portal holds each clinic's (or owner group's) gateway keys,
test and production (the group owner's rule, 2026-09-11). This module:

* works out what a booking still owes (`due`);
* `start`s a payment with the clinic's gateway — the clinic's own credential,
  else its group's, and **never** the platform's: a patient's money must land
  in the clinic's account, not ours;
* `confirm`s the gateway's callback (verified by the adapter, never taken on
  its word) and writes the money inside the clinic's context as an ordinary
  `billing.Payment` — so it shows in the clinic's payments, reports and the
  doctor's share like any other, marked as paid online. A payment in the
  test environment is confirmed on the checkout only, never written to the
  clinic's books.
"""

import secrets
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from subscriptions.entitlements import has_feature
from tenants.context import tenant_context

from . import vault
from .gateways import GatewayError, adapter
from .models import ClinicCheckout, IntegrationCredential

METHODS = [
    IntegrationCredential.Kind.PAYMOB,
    IntegrationCredential.Kind.FAWRY,
    IntegrationCredential.Kind.VODAFONE_CASH,
]
#: A booking in one of these can't be paid for.
UNPAYABLE = {"requested", "cancelled", "no_show"}
METHOD_NAME = "دفع إلكتروني"


def methods_for(tenant, branch):
    """The gateways this clinic can take payments through, [(kind, label)]."""
    if not has_feature(tenant, "online_payments"):
        return []
    found = []
    for kind in METHODS:
        try:
            if vault.resolve(kind, branch=branch, customer=tenant, include_platform=False):
                found.append({"kind": kind, "label": IntegrationCredential.Kind(kind).label})
        except vault.VaultError:
            continue
    return found


def due(appointment):
    """What is left to pay on a booking (call inside the clinic's context)."""
    from billing.models import Payment

    if appointment.status in UNPAYABLE or not appointment.price:
        return Decimal("0")
    paid = Payment.objects.filter(appointment=appointment).aggregate(t=Sum("amount"))["t"] or Decimal("0")
    return max(Decimal(appointment.price) - paid, Decimal("0"))


def start(tenant, appointment, method, *, payer, return_url):
    """Inside the clinic's context. Returns {redirect_url, reference, mode}."""
    if method not in METHODS:
        raise GatewayError("اختر طريقة دفع إلكتروني.")
    if not has_feature(tenant, "online_payments"):
        raise GatewayError("الدفع الإلكتروني غير متاح في باقة هذه العيادة.")
    amount = due(appointment)
    if amount <= 0:
        raise GatewayError("لا يوجد مبلغ مستحق على هذا الحجز.")
    found = vault.resolve(method, branch=appointment.branch, customer=tenant, include_platform=False)
    if found is None:
        raise GatewayError("لم تُفعِّل العيادة هذه الطريقة بعد.")
    config, mode, credential = found
    reference = f"CP-{appointment.pk}-{secrets.token_hex(4)}"
    checkout = ClinicCheckout.objects.create(
        customer=tenant, branch_id=appointment.branch_id, appointment_uuid=appointment.uuid,
        patient_id=appointment.patient_id, amount=amount, method=method, mode=mode,
        credential=credential, reference=reference,
    )
    kwargs = {"amount": amount, "reference": reference, "payer": payer}
    if method == IntegrationCredential.Kind.FAWRY:
        kwargs.update(mode=mode, return_url=return_url)
    try:
        result = adapter(method).start(config, **kwargs)
    except GatewayError:
        checkout.status = ClinicCheckout.Status.FAILED
        checkout.save(update_fields=["status"])
        raise
    return {"redirect_url": result["redirect_url"], "reference": reference, "mode": mode}


@transaction.atomic
def confirm(method, data, reference):
    """The gateway says `reference` was paid: check with the adapter, then
    record the money in the clinic. Repeated callbacks change nothing."""
    checkout = ClinicCheckout.objects.select_for_update().filter(reference=reference, method=method).first()
    if checkout is None:
        raise GatewayError("عملية دفع غير معروفة.")
    if checkout.status == ClinicCheckout.Status.CONFIRMED:
        return checkout
    config = vault.config_of(checkout.credential, checkout.mode)
    extra = {"mode": checkout.mode} if method == IntegrationCredential.Kind.FAWRY else {}
    confirmed_reference, paid, gateway_id = adapter(method).confirm(
        config, data, expected_amount=checkout.amount, **extra
    )
    if confirmed_reference != checkout.reference:
        raise GatewayError("مرجع الدفع لا يطابق.")
    checkout.gateway_id = gateway_id[:80]
    if not paid:
        checkout.status = ClinicCheckout.Status.FAILED
        checkout.save(update_fields=["status", "gateway_id"])
        return checkout
    # A test-environment payment proves the keys work but is not money: it
    # stays on the checkout and out of the clinic's books.
    if checkout.mode == IntegrationCredential.Mode.PRODUCTION:
        checkout.payment_uuid = _record(checkout)
    checkout.status = ClinicCheckout.Status.CONFIRMED
    checkout.confirmed_at = timezone.now()
    checkout.save(update_fields=["status", "gateway_id", "payment_uuid", "confirmed_at"])
    return checkout


def _record(checkout):
    from appointments.models import Appointment
    from billing.models import Payment, PaymentMethod

    tenant = checkout.customer
    with tenant_context(tenant):
        appointment = Appointment.objects.get(uuid=checkout.appointment_uuid)
        method, _ = PaymentMethod.objects.get_or_create(tenant=tenant, name=METHOD_NAME)
        payment = Payment.objects.create(
            tenant=tenant, appointment=appointment, patient_id=checkout.patient_id, method=method,
            receipt_number=checkout.reference, amount=checkout.amount, branch_id=checkout.branch_id,
            notes=f"دفع إلكتروني — {IntegrationCredential.Kind(checkout.method).label} — مرجع البوابة {checkout.gateway_id}",
        )
        return payment.uuid
