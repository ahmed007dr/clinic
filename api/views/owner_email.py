"""The group owner's email settings — one default for the whole group, and an
optional override for each clinic.

    GET    /api/owner/email/                     the default, and every clinic
    PUT    /api/owner/email/<group|branch id>/   save settings
    DELETE /api/owner/email/<group|branch id>/   remove them
    POST   /api/owner/email/<group|branch id>/test/   try a connection
    POST   /api/owner/email/apply-default/       every clinic uses the group's

Which server a message goes out through is decided in platform_admin/mailer.py:
the clinic's own settings, else the group's, else the platform's, else the
server's settings file. This module only lets the Owner manage the first two.
Both live in the same vault records the developer portal edits
(platform_admin/vault.py), so the two screens always agree.

The Owner works on the live set. A record the developer left in the test
environment stays there and is edited in place; a new one goes live at once,
because an Owner has no use for a test/production distinction — the button
"اختبار الاتصال" is their test.
"""

import ipaddress
import socket

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from api.permissions import IsGroupOwner
from audit.models import AuditLog
from branches.models import Branch
from platform_admin import checks, vault
from platform_admin.models import IntegrationCredential

Kind = IntegrationCredential.Kind
Scope = IntegrationCredential.Scope

GROUP = "group"


# ------------------------------------------------------------ helpers


def _lookup(customer, branch):
    return IntegrationCredential.objects.filter(
        kind=Kind.SMTP,
        scope=Scope.CLINIC if branch else Scope.GROUP,
        customer=customer,
        branch=branch,
    ).first()


def _target(request, target):
    """(customer, branch) for `group` or a clinic id — a clinic of this group
    only: the tenant-scoped manager cannot see anyone else's."""
    customer = request.user.tenant
    if target == GROUP:
        return customer, None
    try:
        pk = int(target)
    except (TypeError, ValueError):
        raise NotFound()
    branch = Branch.objects.filter(pk=pk).first()
    if branch is None:
        raise NotFound()
    return customer, branch


def _usable(credential):
    """Whether this record would actually be used to send."""
    if credential is None or not credential.enabled:
        return False
    try:
        return not vault.missing(Kind.SMTP, vault.config_of(credential))
    except vault.VaultError:
        return False


def _item(credential):
    """What the browser may see of one record. Secrets are masked."""
    if credential is None:
        return None
    try:
        values = vault.config_of(credential)
    except vault.VaultError as error:
        return {"error": str(error), "enabled": credential.enabled}
    return {
        "enabled": credential.enabled,
        "mode": credential.mode,
        "values": vault.masked(Kind.SMTP, values),
        "missing": vault.missing(Kind.SMTP, values),
        "updated_at": credential.updated_at,
        "updated_by": getattr(credential.updated_by, "email", None),
    }


def _platform_sends():
    platform = IntegrationCredential.objects.filter(kind=Kind.SMTP, scope=Scope.PLATFORM).first()
    return _usable(platform)


def _audit(request, customer, action, credential, branch):
    AuditLog.objects.create(
        tenant=customer,
        user=request.user,
        action="custom",
        model_name="IntegrationCredential",
        object_id=str(credential.pk or ""),
        # What changed and where — never the values.
        description=f"[owner] email settings {action}: "
        + (f"clinic {branch.pk} ({branch.name})" if branch else "group default"),
        ip_address=request.META.get("REMOTE_ADDR"),
        user_agent=request.META.get("HTTP_USER_AGENT"),
    )


def _check_host(host):
    """Refuse a mail server that is not on the public internet.

    An Owner types this address and the server then connects to it, so without
    a check the screen doubles as a way to probe the hosting network — the
    database, the cPanel API, anything on localhost. Development is exempt so a
    local test mail server still works.
    """
    if settings.DEBUG:
        return
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except (socket.gaierror, UnicodeError):
        raise ValidationError({"host": "تعذّر العثور على خادم البريد بهذا العنوان."})
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%")[0])
        if not ip.is_global:
            raise ValidationError({"host": "عنوان خادم البريد غير مسموح به."})


def _clean(data, previous):
    """Validated settings from a submission; a blank password keeps the stored one."""
    try:
        cleaned = vault.clean(Kind.SMTP, data, previous)
    except vault.VaultError as error:
        raise ValidationError({"detail": str(error)})
    missing = vault.missing(Kind.SMTP, cleaned)
    if missing:
        raise ValidationError({"detail": "بيانات ناقصة: " + "، ".join(missing)})
    if not 1 <= int(cleaned["port"]) <= 65535:
        raise ValidationError({"port": "المنفذ بين 1 و 65535."})
    if cleaned.get("use_ssl") and cleaned.get("use_tls"):
        raise ValidationError({"detail": "اختر SSL أو TLS، وليس الاثنين معاً."})
    try:
        validate_email(cleaned["from_email"])
    except DjangoValidationError:
        raise ValidationError({"from_email": "البريد المُرسِل غير صالح."})
    _check_host(cleaned["host"])
    return cleaned


def _live_config(credential):
    if credential is None:
        return {}
    try:
        return vault.config_of(credential)
    except vault.VaultError:
        return {}


# ------------------------------------------------------------ views


class OwnerEmailView(APIView):
    permission_classes = [IsGroupOwner]

    def get(self, request):
        customer = request.user.tenant
        group = _lookup(customer, None)
        own = {
            credential.branch_id: credential
            for credential in IntegrationCredential.objects.filter(
                kind=Kind.SMTP, scope=Scope.CLINIC, customer=customer
            ).select_related("updated_by")
        }
        if group is not None:
            group = IntegrationCredential.objects.select_related("updated_by").get(pk=group.pk)
        platform = _platform_sends()
        server = bool(getattr(settings, "EMAIL_HOST", ""))

        def source(credential):
            if _usable(credential):
                return "clinic"
            if _usable(group):
                return "group"
            if platform:
                return "platform"
            return "server" if server else "none"

        return Response({
            "fields": vault.FIELDS[Kind.SMTP]["fields"],
            "group": _item(group),
            "branches": [
                {
                    "id": branch.pk,
                    "name": branch.name,
                    "is_active": branch.is_active,
                    "own": _item(own.get(branch.pk)),
                    # Where this clinic's mail actually goes out from.
                    "source": source(own.get(branch.pk)),
                }
                for branch in Branch.objects.order_by("name")
            ],
            "group_source": "group" if _usable(group) else "platform" if platform else "server" if server else "none",
        })


class OwnerEmailTargetView(APIView):
    permission_classes = [IsGroupOwner]

    @transaction.atomic
    def put(self, request, target):
        customer, branch = _target(request, target)
        credential = _lookup(customer, branch)
        created = credential is None
        if created:
            credential = IntegrationCredential(
                kind=Kind.SMTP, scope=Scope.CLINIC if branch else Scope.GROUP,
                customer=customer, branch=branch, mode=IntegrationCredential.Mode.PRODUCTION,
            )
        else:
            credential = IntegrationCredential.objects.select_for_update().get(pk=credential.pk)
        cleaned = _clean(request.data, _live_config(credential))
        # The live environment, so a record the developer left in test is
        # edited where it is used rather than silently split in two.
        field = "production_config" if credential.mode == IntegrationCredential.Mode.PRODUCTION else "test_config"
        setattr(credential, field, vault.seal(cleaned))
        credential.enabled = bool(request.data.get("enabled", True))
        credential.updated_by = request.user
        try:
            credential.save()
        except IntegrityError:
            raise ValidationError({"detail": "هذا الإعداد مضبوط بالفعل."})
        _audit(request, customer, "added" if created else "changed", credential, branch)
        return Response(_item(credential), status=201 if created else 200)

    def delete(self, request, target):
        customer, branch = _target(request, target)
        credential = _lookup(customer, branch)
        if credential is None:
            raise NotFound()
        _audit(request, customer, "removed", credential, branch)
        credential.delete()
        return Response(status=204)


class OwnerEmailTestView(APIView):
    """Open a connection to the mail server and log in — sends nothing. Tries
    the submitted values (a blank password falls back to the saved one), so the
    Owner can check before saving."""

    permission_classes = [IsGroupOwner]

    def post(self, request, target):
        customer, branch = _target(request, target)
        credential = _lookup(customer, branch)
        cleaned = _clean(request.data, _live_config(credential))
        try:
            message = checks._smtp(cleaned, "production")
        except checks.CheckFailed as error:
            return Response({"ok": False, "detail": str(error)})
        return Response({"ok": True, "detail": message})


class OwnerEmailApplyDefaultView(APIView):
    """Make every clinic send through the group's default: removes each clinic's
    own settings in one step. Refused unless the default can actually send —
    otherwise the clinics would be left with no mail server at all."""

    permission_classes = [IsGroupOwner]

    @transaction.atomic
    def post(self, request):
        customer = request.user.tenant
        if not _usable(_lookup(customer, None)):
            raise ValidationError({"detail": "اضبط الإعداد الافتراضي للمجموعة وفعّله أولاً."})
        own = IntegrationCredential.objects.filter(kind=Kind.SMTP, scope=Scope.CLINIC, customer=customer)
        cleared = own.count()
        for credential in own.select_related("branch"):
            _audit(request, customer, "removed", credential, credential.branch)
        own.delete()
        return Response({"cleared": cleared})
