"""Creating email accounts on the platform's cPanel for an owner group or one
of its clinics — from the developer portal (the group owner's rule,
2026-09-11).

Uses cPanel's UAPI (`Email::add_pop`) with the platform's cPanel credential
from the vault. The new mailbox can immediately become the group's or clinic's
sender: its SMTP settings are stored as that scope's `smtp` credential, so the
doctor emails and reports of that clinic go out from its own address.
"""

import json
import secrets
import string
import urllib.error
import urllib.parse
import urllib.request

from django.db import transaction

from . import vault
from .models import IntegrationCredential, Mailbox

TIMEOUT = 20
LOCAL_PART_CHARS = set(string.ascii_lowercase + string.digits + "._-")


class MailboxError(RuntimeError):
    """The message is for the operator."""


def _cpanel():
    found = vault.resolve(IntegrationCredential.Kind.CPANEL)
    if found is None:
        raise MailboxError("اضبط بيانات cPanel أولاً من «المفاتيح والتكاملات».")
    return found[0]


def _call(config, function, **params):
    url = f"{config['host'].rstrip('/')}/execute/Email/{function}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"Authorization": f"cpanel {config['username']}:{config['api_token']}"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            body = json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as error:
        raise MailboxError(f"رفض cPanel الطلب ({error.code}). راجع اسم المستخدم والـ API Token.")
    except (urllib.error.URLError, TimeoutError, ValueError):
        raise MailboxError("تعذّر الاتصال بـ cPanel.")
    if not body.get("status"):
        errors = body.get("errors") or ["خطأ غير معروف."]
        raise MailboxError("cPanel: " + "؛ ".join(str(e) for e in errors))
    return body.get("data")


def check_connection(config=None):
    """For the portal's "test" button: lists mailboxes without changing any."""
    config = config or _cpanel()
    _call(config, "list_pops")
    return config["domain"]


def new_password():
    alphabet = string.ascii_letters + string.digits + "!@#%^*-_"
    return "".join(secrets.choice(alphabet) for _ in range(20))


@transaction.atomic
def create(customer, local_part, *, branch=None, quota_mb=1024, use_for_sending=True, actor=None):
    """Create `local_part@<platform domain>`; returns (mailbox, password).
    The password is shown once and, if used for sending, kept only in the
    vault."""
    local_part = (local_part or "").strip().lower()
    if not local_part or not set(local_part) <= LOCAL_PART_CHARS or local_part[0] in "._-":
        raise MailboxError("اسم الإيميل بحروف إنجليزية صغيرة وأرقام فقط (ويمكن . _ -).")
    config = _cpanel()
    address = f"{local_part}@{config['domain']}"
    if Mailbox.objects.filter(address=address).exists():
        raise MailboxError("هذا الإيميل موجود بالفعل.")
    password = new_password()
    _call(config, "add_pop", email=local_part, domain=config["domain"], password=password, quota=int(quota_mb))
    mailbox = Mailbox.objects.create(
        customer=customer, branch=branch, address=address, quota_mb=quota_mb,
        used_for_sending=use_for_sending, created_by=actor,
    )
    if use_for_sending:
        smtp = {
            "host": config.get("smtp_host") or f"mail.{config['domain']}", "port": "465",
            "username": address, "password": password, "from_email": address,
            "use_ssl": True, "use_tls": False,
        }
        scope = IntegrationCredential.Scope.CLINIC if branch is not None else IntegrationCredential.Scope.GROUP
        credential, _ = IntegrationCredential.objects.get_or_create(
            kind=IntegrationCredential.Kind.SMTP, scope=scope, customer=customer, branch=branch,
        )
        credential.test_config = vault.seal(smtp)
        credential.production_config = vault.seal(smtp)
        credential.mode = IntegrationCredential.Mode.PRODUCTION
        credential.enabled = True
        credential.notes = f"أُنشئ مع الإيميل {address}"
        credential.updated_by = actor
        credential.save()
    return mailbox, password
