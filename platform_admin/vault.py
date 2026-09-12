"""Integration keys and passwords, encrypted, and the rules for finding them.

Operators enter every key in the developer portal (the group owner's rule,
2026-09-11); this module is the only code that reads or writes them.

* **At rest**: each environment's settings are one JSON object, encrypted with
  Fernet (AES-128-CBC + HMAC-SHA256). The key comes from `PLATFORM_VAULT_KEY`
  in the environment; without it, one is derived from `DJANGO_SECRET_KEY` —
  which works, but means rotating the secret key makes every stored secret
  unreadable. Set PLATFORM_VAULT_KEY in production and keep it with the
  database backups.
* **On the wire**: secret fields are never returned; the browser sees whether
  one is set and its last four characters.
* **Resolution**: the most specific enabled credential wins — the clinic's own,
  then its owner group's, then the platform's — in whichever environment
  (`mode`) it is set to.
"""

import base64
import json
import os

from django.conf import settings

from .models import IntegrationCredential

Kind = IntegrationCredential.Kind
Scope = IntegrationCredential.Scope

#: What each integration asks for. `secret` fields are encrypted and masked;
#: `scopes` says where it may be set.
FIELDS = {
    Kind.SMTP: {
        "scopes": [Scope.PLATFORM, Scope.GROUP, Scope.CLINIC],
        "fields": [
            {"name": "host", "label": "خادم البريد", "required": True},
            {"name": "port", "label": "المنفذ", "required": True, "type": "number"},
            {"name": "username", "label": "اسم المستخدم", "required": True},
            {"name": "password", "label": "كلمة المرور", "secret": True, "required": True},
            {"name": "from_email", "label": "البريد المُرسِل", "required": True},
            {"name": "use_ssl", "label": "SSL", "type": "bool"},
            {"name": "use_tls", "label": "TLS", "type": "bool"},
        ],
    },
    Kind.CPANEL: {
        "scopes": [Scope.PLATFORM],
        "fields": [
            {"name": "host", "label": "رابط cPanel (مثل https://server:2083)", "required": True},
            {"name": "username", "label": "اسم مستخدم cPanel", "required": True},
            {"name": "api_token", "label": "API Token", "secret": True, "required": True},
            {"name": "domain", "label": "الدومين للإيميلات", "required": True},
            {"name": "smtp_host", "label": "خادم SMTP للإيميلات المنشأة (مثل mail.domain.com)"},
        ],
    },
    Kind.PAYMOB: {
        "scopes": [Scope.PLATFORM, Scope.GROUP, Scope.CLINIC],
        "fields": [
            {"name": "api_key", "label": "API Key", "secret": True, "required": True},
            {"name": "card_integration_id", "label": "Integration ID (بطاقات)", "required": True},
            {"name": "iframe_id", "label": "iFrame ID", "required": True},
            {"name": "hmac_secret", "label": "HMAC Secret", "secret": True, "required": True},
        ],
    },
    Kind.FAWRY: {
        "scopes": [Scope.PLATFORM, Scope.GROUP, Scope.CLINIC],
        "fields": [
            {"name": "merchant_code", "label": "Merchant Code", "required": True},
            {"name": "security_key", "label": "Security Key", "secret": True, "required": True},
        ],
    },
    Kind.VODAFONE_CASH: {
        # Through Paymob's mobile-wallet integration: its own integration id,
        # the Paymob account's key and HMAC secret.
        "scopes": [Scope.PLATFORM, Scope.GROUP, Scope.CLINIC],
        "fields": [
            {"name": "api_key", "label": "Paymob API Key", "secret": True, "required": True},
            {"name": "wallet_integration_id", "label": "Integration ID (المحافظ)", "required": True},
            {"name": "hmac_secret", "label": "HMAC Secret", "secret": True, "required": True},
        ],
    },
    Kind.GOOGLE_DRIVE: {
        "scopes": [Scope.PLATFORM],
        "fields": [
            {"name": "service_account_json", "label": "ملف Service Account (JSON)", "secret": True,
             "required": True, "type": "textarea"},
            {"name": "folder_id", "label": "Folder ID", "required": True},
        ],
    },
}


class VaultError(ValueError):
    """The message is for the operator."""


# ------------------------------------------------------------ encryption


def _fernet():
    from cryptography.fernet import Fernet

    key = os.environ.get("PLATFORM_VAULT_KEY") or getattr(settings, "PLATFORM_VAULT_KEY", "")
    if not key:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF

        derived = HKDF(
            algorithm=hashes.SHA256(), length=32, salt=b"clinic-platform-vault", info=b"fernet",
        ).derive(settings.SECRET_KEY.encode())
        key = base64.urlsafe_b64encode(derived)
    return Fernet(key)


def seal(values):
    return _fernet().encrypt(json.dumps(values or {}).encode()).decode() if values else ""


def unseal(blob):
    if not blob:
        return {}
    from cryptography.fernet import InvalidToken

    try:
        return json.loads(_fernet().decrypt(blob.encode()))
    except InvalidToken:
        raise VaultError("تعذّر فك تشفير الإعدادات: تغيّر مفتاح التشفير. أعد إدخالها.")


# ------------------------------------------------------------ shape and masking


def spec(kind):
    try:
        return FIELDS[kind]
    except KeyError:
        raise VaultError("نوع تكامل غير معروف.")


def clean(kind, submitted, previous):
    """Validate one environment's submitted values. A secret left blank keeps
    what was stored; everything else is taken as given."""
    submitted = submitted or {}
    cleaned = {}
    for field in spec(kind)["fields"]:
        name = field["name"]
        value = submitted.get(name, "")
        if field.get("type") == "bool":
            cleaned[name] = bool(value)
            continue
        value = str(value if value is not None else "").strip()
        if field.get("secret") and not value:
            value = previous.get(name, "")
        if field.get("type") == "number" and value:
            if not value.isdigit():
                raise VaultError(f"{field['label']}: رقم فقط.")
        if field.get("name") == "service_account_json" and value and value != previous.get(name):
            try:
                parsed = json.loads(value)
                assert parsed.get("client_email") and parsed.get("private_key")
            except Exception:
                raise VaultError("ملف Service Account غير صالح.")
        cleaned[name] = value
    return cleaned


def masked(kind, values):
    """What the browser may see: plain fields, and for secrets only whether
    they are set and their last four characters."""
    out = {}
    for field in spec(kind)["fields"]:
        value = values.get(field["name"])
        if field.get("secret"):
            out[field["name"]] = {"set": bool(value), "hint": f"…{str(value)[-4:]}" if value else ""}
        else:
            out[field["name"]] = value if value is not None else ""
    return out


def missing(kind, values):
    return [f["label"] for f in spec(kind)["fields"] if f.get("required") and not values.get(f["name"])]


def config_of(credential, mode=None):
    mode = mode or credential.mode
    return unseal(credential.production_config if mode == "production" else credential.test_config)


def payload(credential):
    test = unseal(credential.test_config)
    production = unseal(credential.production_config)
    return {
        "id": credential.pk,
        "kind": credential.kind,
        "kind_label": credential.get_kind_display(),
        "scope": credential.scope,
        "scope_label": credential.get_scope_display(),
        "customer": str(credential.customer.uuid) if credential.customer_id else None,
        "customer_name": credential.customer.name if credential.customer_id else None,
        "branch": credential.branch_id,
        "mode": credential.mode,
        "enabled": credential.enabled,
        "notes": credential.notes,
        "test": masked(credential.kind, test),
        "production": masked(credential.kind, production),
        "test_missing": missing(credential.kind, test),
        "production_missing": missing(credential.kind, production),
        "updated_at": credential.updated_at,
        "updated_by": getattr(credential.updated_by, "email", None),
    }


# ------------------------------------------------------------ resolution


def resolve(kind, *, branch=None, customer=None, include_platform=True):
    """The live settings for `kind` here: the clinic's own, else its group's,
    else the platform's — or None. Returns (values, mode, credential).

    `include_platform=False` for a clinic collecting from its own patients:
    that money must reach the clinic's account, never fall back to the
    platform's."""
    candidates = []
    if branch is not None:
        candidates.append({"scope": Scope.CLINIC, "branch_id": branch.pk})
        customer = customer or getattr(branch, "tenant", None)
    if customer is not None:
        candidates.append({"scope": Scope.GROUP, "customer_id": customer.pk})
    if include_platform:
        candidates.append({"scope": Scope.PLATFORM})
    for lookup in candidates:
        credential = IntegrationCredential.objects.filter(kind=kind, enabled=True, **lookup).first()
        if credential is None:
            continue
        values = unseal(credential.production_config if credential.mode == "production" else credential.test_config)
        if not missing(kind, values):
            return values, credential.mode, credential
    return None
