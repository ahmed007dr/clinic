"""Online payment gateways — Paymob (cards), Vodafone Cash (Paymob mobile
wallets) and Fawry — each in a test and a production environment.

Keys come from the vault (platform_admin/vault.py): the platform's own for
collecting subscriptions, a group's or a clinic's own for collecting from its
patients. Every adapter does the same two things:

* `start(...)` creates the payment at the gateway and returns where to send
  the payer (`redirect_url`), with our `reference` to match it back;
* `confirm(...)` decides whether a callback really is a completed payment of
  the expected amount — **never from the callback's word alone**: Paymob's is
  checked against its HMAC-SHA512 over the documented field list; Fawry's by
  asking Fawry for the payment's status with a signed request.

Written against the gateways' published API documentation. They are not
exercised against a live sandbox here — run one test payment per gateway in
the test environment before switching a credential to production.
"""

import hashlib
import hmac
import json
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal

TIMEOUT = 20


class GatewayError(RuntimeError):
    """The message is for the operator or the payer."""


def _request(method, url, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            raw = response.read().decode() or "{}"
    except urllib.error.HTTPError as error:
        raise GatewayError(f"رفضت بوابة الدفع الطلب ({error.code}).")
    except (urllib.error.URLError, TimeoutError):
        raise GatewayError("تعذّر الاتصال ببوابة الدفع.")
    try:
        return json.loads(raw)
    except ValueError:
        return raw.strip().strip('"')


def cents(amount):
    return int((Decimal(amount) * 100).quantize(Decimal("1")))


# ------------------------------------------------------------------ Paymob

PAYMOB_BASE = "https://accept.paymob.com"

#: The fields Paymob signs, in the order it concatenates them (its "HMAC
#: calculation" documentation for transaction callbacks).
PAYMOB_HMAC_FIELDS = [
    "amount_cents", "created_at", "currency", "error_occured", "has_parent_transaction", "id",
    "integration_id", "is_3d_secure", "is_auth", "is_capture", "is_refunded", "is_standalone_payment",
    "is_voided", "order.id", "owner", "pending", "source_data.pan", "source_data.sub_type",
    "source_data.type", "success",
]


def _flatten(obj, prefix=""):
    flat = {}
    for key, value in (obj or {}).items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{name}."))
        else:
            flat[name] = value
    return flat


def _paymob_string(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    return "" if value is None else str(value)


def paymob_signature(transaction, secret):
    flat = _flatten(transaction)
    # A redirect's query string names the order `order` rather than `order.id`.
    if "order.id" not in flat and "order" in flat:
        flat["order.id"] = flat["order"]
    message = "".join(_paymob_string(flat.get(field)) for field in PAYMOB_HMAC_FIELDS)
    return hmac.new(secret.encode(), message.encode(), hashlib.sha512).hexdigest()


def _paymob_payment_key(config, amount, reference, payer, integration_id):
    auth = _request("POST", f"{PAYMOB_BASE}/api/auth/tokens", {"api_key": config["api_key"]})
    token = auth.get("token") if isinstance(auth, dict) else None
    if not token:
        raise GatewayError("مفتاح Paymob غير صالح.")
    order = _request("POST", f"{PAYMOB_BASE}/api/ecommerce/orders", {
        "auth_token": token, "delivery_needed": False, "amount_cents": cents(amount),
        "currency": "EGP", "merchant_order_id": reference, "items": [],
    })
    billing = {
        "first_name": payer.get("name") or "Clinic", "last_name": "-", "email": payer.get("email") or "na@na.na",
        "phone_number": payer.get("phone") or "+200000000000", "apartment": "NA", "floor": "NA",
        "street": "NA", "building": "NA", "shipping_method": "NA", "postal_code": "NA",
        "city": "NA", "country": "EG", "state": "NA",
    }
    key = _request("POST", f"{PAYMOB_BASE}/api/acceptance/payment_keys", {
        "auth_token": token, "amount_cents": cents(amount), "expiration": 3600,
        "order_id": order.get("id"), "billing_data": billing, "currency": "EGP",
        "integration_id": int(integration_id),
    })
    if not isinstance(key, dict) or not key.get("token"):
        raise GatewayError("تعذّر إنشاء عملية الدفع في Paymob.")
    return key["token"]


class Paymob:
    kind = "paymob"

    def start(self, config, *, amount, reference, payer):
        token = _paymob_payment_key(config, amount, reference, payer, config["card_integration_id"])
        return {"redirect_url": f"{PAYMOB_BASE}/api/acceptance/iframes/{config['iframe_id']}?payment_token={token}"}

    def confirm(self, config, data, *, expected_amount):
        """`data`: the webhook's `obj`, or a redirect's query parameters, with
        its `hmac`. Returns (reference, paid, gateway_id)."""
        transaction = data.get("obj", data)
        signature = data.get("hmac") or transaction.get("hmac") or ""
        if not hmac.compare_digest(paymob_signature(transaction, config["hmac_secret"]), str(signature)):
            raise GatewayError("توقيع Paymob غير صحيح.")
        flat = _flatten(transaction)
        reference = flat.get("order.merchant_order_id") or flat.get("merchant_order_id") or ""
        paid = _paymob_string(flat.get("success")) == "true" and _paymob_string(flat.get("pending")) != "true"
        if paid and int(flat.get("amount_cents") or 0) != cents(expected_amount):
            raise GatewayError("المبلغ المدفوع لا يطابق المستحق.")
        return reference, paid, str(flat.get("id", ""))


class VodafoneCash(Paymob):
    """Vodafone Cash (and other Egyptian mobile wallets) through Paymob: the
    same account, a wallet integration, and the payer's wallet number."""

    kind = "vodafone_cash"

    def start(self, config, *, amount, reference, payer):
        phone = payer.get("phone")
        if not phone:
            raise GatewayError("اكتب رقم محفظة فودافون كاش.")
        token = _paymob_payment_key(config, amount, reference, payer, config["wallet_integration_id"])
        result = _request("POST", f"{PAYMOB_BASE}/api/acceptance/payments/pay", {
            "source": {"identifier": phone, "subtype": "WALLET"}, "payment_token": token,
        })
        url = result.get("redirect_url") or result.get("iframe_redirection_url") if isinstance(result, dict) else None
        if not url:
            raise GatewayError("تعذّر بدء الدفع بالمحفظة.")
        return {"redirect_url": url}


# ------------------------------------------------------------------ Fawry

FAWRY_BASE = {
    "test": "https://atfawry.fawrystaging.com",
    "production": "https://www.atfawry.com",
}


def _sha256(*parts):
    return hashlib.sha256("".join(str(p) for p in parts).encode()).hexdigest()


class Fawry:
    kind = "fawry"

    def start(self, config, *, amount, reference, payer, mode="test", return_url=""):
        price = f"{Decimal(amount):.2f}"
        profile = payer.get("id") or reference
        item_id = "subscription"
        body = {
            "merchantCode": config["merchant_code"],
            "merchantRefNum": reference,
            "customerProfileId": profile,
            "customerMobile": payer.get("phone") or "",
            "customerEmail": payer.get("email") or "",
            "customerName": payer.get("name") or "",
            "language": "ar-eg",
            "chargeItems": [{"itemId": item_id, "description": payer.get("description") or "Payment",
                             "price": price, "quantity": 1}],
            "returnUrl": return_url,
            "signature": _sha256(config["merchant_code"], reference, profile, return_url, item_id, 1, price,
                                 config["security_key"]),
        }
        url = _request("POST", f"{FAWRY_BASE[mode]}/fawrypay-api/api/payments/init", body)
        if not isinstance(url, str) or not url.startswith("http"):
            raise GatewayError("تعذّر بدء الدفع عبر فوري.")
        return {"redirect_url": url}

    def confirm(self, config, data, *, expected_amount, mode="test"):
        """Ask Fawry itself — the callback's parameters only say which
        payment to ask about. Returns (reference, paid, fawry_reference)."""
        reference = data.get("merchantRefNumber") or data.get("merchantRefNum") or ""
        if not reference:
            raise GatewayError("مرجع الدفع غير موجود.")
        query = urllib.parse.urlencode({
            "merchantCode": config["merchant_code"], "merchantRefNumber": reference,
            "signature": _sha256(config["merchant_code"], reference, config["security_key"]),
        })
        status = _request("GET", f"{FAWRY_BASE[mode]}/ECommerceWeb/Fawry/payments/status/v2?{query}")
        if not isinstance(status, dict):
            raise GatewayError("رد فوري غير مفهوم.")
        paid = status.get("orderStatus") == "PAID"
        if paid and Decimal(str(status.get("paymentAmount", 0))) < Decimal(expected_amount):
            raise GatewayError("المبلغ المدفوع لا يطابق المستحق.")
        return reference, paid, str(status.get("fawryRefNumber", ""))


def reference_in(data):
    """Our reference in a callback, whatever shape the gateway sent it in —
    only to find the payment; `confirm` then verifies it."""
    obj = data.get("obj") if isinstance(data.get("obj"), dict) else {}
    order = obj.get("order") if isinstance(obj.get("order"), dict) else {}
    return str(
        data.get("merchantRefNumber") or data.get("merchantRefNum") or data.get("merchant_order_id")
        or order.get("merchant_order_id") or ""
    )


ADAPTERS = {"paymob": Paymob(), "vodafone_cash": VodafoneCash(), "fawry": Fawry()}


def adapter(kind):
    try:
        return ADAPTERS[kind]
    except KeyError:
        raise GatewayError("بوابة دفع غير معروفة.")
