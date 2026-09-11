"""The developer portal's "test connection" button, one per integration.

Each check uses one environment's stored settings, changes nothing anywhere,
and returns a sentence for the operator — or raises CheckFailed with one.
"""

from django.core.mail import get_connection

from . import vault
from .gateways import PAYMOB_BASE, GatewayError, _request
from .mailboxes import MailboxError, check_connection
from .models import IntegrationCredential

Kind = IntegrationCredential.Kind


class CheckFailed(RuntimeError):
    pass


def _smtp(config, mode):
    try:
        connection = get_connection(
            backend="django.core.mail.backends.smtp.EmailBackend",
            host=config["host"], port=int(config["port"]), username=config["username"],
            password=config["password"], use_ssl=bool(config.get("use_ssl")),
            use_tls=bool(config.get("use_tls")) and not config.get("use_ssl"), timeout=10,
        )
        connection.open()
        connection.close()
    except Exception as error:  # noqa: BLE001 — any failure is the answer
        raise CheckFailed(f"تعذّر الدخول إلى خادم البريد: {error.__class__.__name__}")
    return f"تم الاتصال بخادم البريد {config['host']} بنجاح."


def _cpanel(config, mode):
    try:
        domain = check_connection(config)
    except MailboxError as error:
        raise CheckFailed(str(error))
    return f"تم الاتصال بـ cPanel — الدومين {domain}."


def _paymob(config, mode):
    try:
        auth = _request("POST", f"{PAYMOB_BASE}/api/auth/tokens", {"api_key": config["api_key"]})
    except GatewayError as error:
        raise CheckFailed(str(error))
    if not (isinstance(auth, dict) and auth.get("token")):
        raise CheckFailed("مفتاح Paymob غير صالح.")
    return "مفتاح Paymob صالح. نفّذ عملية دفع تجريبية قبل التحويل إلى الإنتاج."


def _fawry(config, mode):
    # Fawry has no key-check call; a payment in the test environment is the
    # real test. The settings are at least complete.
    return "بيانات فوري مكتملة. لا يوفر فوري اختبار اتصال — نفّذ عملية دفع تجريبية."


def _drive(config, mode):
    from .gdrive import DriveError, check

    try:
        name = check(config)
    except DriveError as error:
        raise CheckFailed(str(error))
    return f"تم الوصول إلى مجلد Google Drive «{name}»."


CHECKS = {
    Kind.SMTP: _smtp,
    Kind.CPANEL: _cpanel,
    Kind.PAYMOB: _paymob,
    Kind.VODAFONE_CASH: _paymob,
    Kind.FAWRY: _fawry,
    Kind.GOOGLE_DRIVE: _drive,
}


def run(credential, mode):
    config = vault.config_of(credential, mode)
    missing = vault.missing(credential.kind, config)
    if missing:
        raise CheckFailed("بيانات ناقصة: " + "، ".join(missing))
    return CHECKS[credential.kind](config, mode)

