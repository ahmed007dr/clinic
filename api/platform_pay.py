"""Online payments: the group owner paying the platform, and every gateway's
callback (docs/06 PLAT-002).

* The owner's side: the group's subscription invoices and balance, and paying
  an invoice through the **platform's** gateway (platform_admin/online.py).
* `/api/pay/<method>/callback/`: where Paymob, Fawry and Vodafone Cash report
  back — both the server-to-server notification (POST) and the payer's
  browser coming back (GET). The reference says whose payment it is: `PP-`
  a platform invoice, `CP-` a patient paying a clinic
  (platform_admin/clinic_pay.py). Nothing is believed from the callback
  itself; each adapter verifies it (signature or a signed status query).
"""

import logging

from django.http import HttpResponseRedirect
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from platform_admin import billing, clinic_pay, online, vault
from platform_admin.gateways import GatewayError, reference_in
from platform_admin.models import IntegrationCredential, PlatformInvoice, PlatformPayment
from tenants.context import get_current_tenant

from .permissions import IsGroupOwner
from .platform_business import invoice_payload, payment_payload

logger = logging.getLogger(__name__)
Kind = IntegrationCredential.Kind
GATEWAYS = (Kind.PAYMOB, Kind.FAWRY, Kind.VODAFONE_CASH)


def platform_methods():
    """Gateways the platform itself collects subscriptions through."""
    found = []
    for kind in GATEWAYS:
        try:
            if vault.resolve(kind):
                found.append({"kind": kind, "label": Kind(kind).label})
        except vault.VaultError:
            continue
    return found


class OwnerInvoicesView(APIView):
    """The group's subscription invoices, payments and balance."""

    permission_classes = [IsGroupOwner]

    def get(self, request):
        tenant = get_current_tenant()
        invoices = PlatformInvoice.objects.filter(customer=tenant).prefetch_related("payments")
        payments = PlatformPayment.objects.filter(customer=tenant).select_related("invoice")
        return Response({
            "account": billing.account(tenant),
            "invoices": [invoice_payload(i) for i in invoices],
            "payments": [payment_payload(p) for p in payments[:100]],
            "methods": platform_methods(),
        })


class OwnerInvoicePayView(APIView):
    """Start paying one invoice online; returns where to send the browser."""

    permission_classes = [IsGroupOwner]

    def post(self, request, pk):
        tenant = get_current_tenant()
        invoice = PlatformInvoice.objects.filter(pk=pk, customer=tenant).first()
        if invoice is None:
            return Response({"detail": "الفاتورة غير موجودة."}, status=404)
        method = request.data.get("method")
        payer = {
            "name": request.user.get_full_name() or tenant.name,
            "email": request.user.email,
            "phone": str(request.data.get("phone") or "").strip(),
            "id": str(tenant.uuid),
            "description": f"{invoice.number} — {invoice.description}",
        }
        try:
            result = online.start(
                invoice, method, payer=payer, actor=request.user,
                return_url=request.build_absolute_uri(f"/api/pay/{method}/callback/"),
            )
        except GatewayError as error:
            return Response({"detail": str(error)}, status=400)
        return Response(result)


class GatewayCallbackView(APIView):
    """Open to the internet by nature; trusts nothing it is told."""

    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def _settle(self, method, data):
        """(kind, outcome, checkout-or-payment): kind "platform" or "clinic"."""
        reference = reference_in(data)
        if reference.startswith("CP-"):
            checkout = clinic_pay.confirm(method, data, reference)
            return "clinic", checkout.status, checkout
        payment = online.confirm(method, data)
        return "platform", payment.status, payment

    def _data(self, request):
        data = request.query_params.dict()
        if isinstance(request.data, dict):
            data.update(request.data)
        # Paymob signs the webhook with an `hmac` in the query string.
        if request.query_params.get("hmac") and "hmac" not in data:
            data["hmac"] = request.query_params["hmac"]
        return data

    def post(self, request, method):
        if method not in GATEWAYS:
            return Response({"detail": "unknown gateway"}, status=404)
        try:
            self._settle(method, self._data(request))
        except (GatewayError, vault.VaultError, KeyError, ValueError) as error:
            logger.warning("Rejected %s callback: %s", method, error)
            return Response({"detail": str(error)}, status=400)
        return Response({"ok": True})

    def get(self, request, method):
        """The payer's browser, back from the gateway: settle, then send them
        to the page they paid from with the outcome."""
        if method not in GATEWAYS:
            return HttpResponseRedirect("/app/")
        try:
            kind, outcome, record = self._settle(method, self._data(request))
        except (GatewayError, vault.VaultError, KeyError, ValueError) as error:
            logger.warning("Rejected %s return: %s", method, error)
            return HttpResponseRedirect("/app/?payment=failed")
        result = "ok" if outcome in ("confirmed",) else "failed"
        if kind == "clinic":
            return HttpResponseRedirect(f"/app/portal/{record.customer.slug}/?payment={result}")
        return HttpResponseRedirect(f"/app/subscription?payment={result}")


