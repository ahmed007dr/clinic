"""Which mail server a clinic's emails go out through.

The clinic's own SMTP settings if the operator set them (or created it a
mailbox), else its owner group's, else the platform's — all from the vault
(platform_admin/vault.py) — and only then the server's settings file.
"""

from django.conf import settings
from django.core.mail import get_connection

from . import vault
from .models import IntegrationCredential

TIMEOUT = 10


def sender_for(*, branch=None, customer=None):
    """(connection, from_email), or (None, None) when no mail server is set
    up anywhere — the caller then sends nothing."""
    found = vault.resolve(IntegrationCredential.Kind.SMTP, branch=branch, customer=customer)
    if found is not None:
        config = found[0]
        connection = get_connection(
            backend="django.core.mail.backends.smtp.EmailBackend",
            host=config["host"], port=int(config["port"]), username=config["username"],
            password=config["password"], use_ssl=bool(config.get("use_ssl")),
            use_tls=bool(config.get("use_tls")) and not config.get("use_ssl"), timeout=TIMEOUT,
        )
        return connection, config["from_email"]
    if getattr(settings, "EMAIL_HOST", None) or "locmem" in settings.EMAIL_BACKEND:
        return get_connection(timeout=TIMEOUT), settings.DEFAULT_FROM_EMAIL
    return None, None
