"""The email log — what the system sent, to whom, and exactly what it said.

    GET /api/email-log/                          a clinic's Admin / the group Owner
    GET /api/email-log/<uuid>/                   one message in full, with its history
    POST /api/email-log/<uuid>/resend/           send it again to the same recipient
    GET /api/platform/tenants/<uuid>/email-log/  platform staff (support too)
    GET /api/platform/tenants/<uuid>/email-log/<uuid>/

Filters (all optional): `q` (recipient address or subject), `kind`, `status`,
`branch` (a clinic's id — for the Owner, who sees them all), `from` and `to`
(dates). The list answers with the page of messages, the count
that matches, and a count per kind for the filter chips; a message's body is
returned only by the detail request, so a page stays small.

Re-sending sends the stored text unchanged, only to the address it first went
to (so it is never a way to mail a clinic's figures somewhere new), and records
a new row pointing at the original — that is the "when was it sent, and how many
times" history. Messages that carry a credential are not stored, so they cannot
be re-sent. Platform staff read; they do not re-send.

Who sees what: the Owner sees every clinic of the group, an Admin only their
own (`scope_queryset_to_user`), platform staff one group at a time inside its
tenant context — and opening a group's log is written to its audit trail like
every other platform read (platform_admin/audit.py).
"""

from django.core.cache import cache
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_date
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.roles import scope_queryset_to_user
from api.pagination import ClinicPagination
from api.permissions import IsClinicAdmin
from api.platform import IsPlatformStaff
from audit.models import AuditLog
from notifications.maillog import KINDS, RESENDABLE, deliver
from notifications.models import EmailLog
from platform_admin.audit import record
from platform_admin.mailer import sender_for
from tenants.context import tenant_context
from tenants.models import Tenant


def _row(entry):
    return {
        "id": str(entry.uuid),
        "kind": entry.kind,
        "kind_label": KINDS.get(entry.kind, KINDS["other"]),
        "to": entry.to_address,
        "subject": entry.subject,
        "status": entry.status,
        "status_label": entry.get_status_display(),
        "error": entry.error,
        "branch": entry.branch_id,
        "branch_name": entry.branch.name if entry.branch_id else None,
        "is_resend": entry.resent_from_id is not None,
        "created_at": entry.created_at,
    }


def _history(entry):
    """Every send of this message — the first, then each re-send — oldest first."""
    root = entry.resent_from or entry
    sends = [root, *root.resends.order_by("created_at", "id")]
    return [
        {
            "id": str(send.uuid), "created_at": send.created_at, "status": send.status,
            "status_label": send.get_status_display(), "is_resend": send.pk != root.pk,
        }
        for send in sends
    ]


def _detail(entry):
    return {
        **_row(entry),
        "from": entry.from_address,
        "body": entry.body,
        "is_html": entry.is_html,
        "template": entry.template,
        "resendable": entry.kind in RESENDABLE,
        "history": _history(entry),
    }


def _date(params, key):
    raw = params.get(key)
    if not raw:
        return None
    value = parse_date(raw)
    if value is None:
        raise ValidationError({key: "تاريخ غير صالح."})
    return value


def _filtered(queryset, params):
    """Everything except the kind filter, and the kind filter separately — so
    the per-kind counts still show what the other filters would leave."""
    text = (params.get("q") or "").strip()
    if text:
        queryset = queryset.filter(Q(to_address__icontains=text) | Q(subject__icontains=text))
    if params.get("status") in EmailLog.Status.values:
        queryset = queryset.filter(status=params["status"])
    if params.get("branch"):
        try:
            queryset = queryset.filter(branch_id=int(params["branch"]))
        except (TypeError, ValueError):
            raise ValidationError({"branch": "عيادة غير صالحة."})
    start, end = _date(params, "from"), _date(params, "to")
    if start:
        queryset = queryset.filter(created_at__date__gte=start)
    if end:
        queryset = queryset.filter(created_at__date__lte=end)
    return queryset


def _list(request, queryset):
    params = request.query_params
    base = _filtered(queryset, params)
    by_kind = {row["kind"]: row["n"] for row in base.values("kind").annotate(n=Count("id"))}
    matching = base.filter(kind=params["kind"]) if params.get("kind") else base
    paginator = ClinicPagination()
    page = paginator.paginate_queryset(matching.select_related("branch"), request)
    response = paginator.get_paginated_response([_row(entry) for entry in page])
    response.data["by_kind"] = [
        {"kind": kind, "label": label, "count": by_kind.get(kind, 0)} for kind, label in KINDS.items()
    ]
    response.data["failed"] = matching.filter(status=EmailLog.Status.FAILED).count()
    return response


def _one(queryset, uuid):
    try:
        return queryset.select_related("branch").get(uuid=uuid)
    except EmailLog.DoesNotExist:
        raise NotFound()


class EmailLogListView(APIView):
    permission_classes = [IsClinicAdmin]

    def get(self, request):
        return _list(request, scope_queryset_to_user(EmailLog.objects.all(), request.user))


class EmailLogDetailView(APIView):
    permission_classes = [IsClinicAdmin]

    def get(self, request, uuid):
        queryset = scope_queryset_to_user(EmailLog.objects.all(), request.user)
        return Response(_detail(_one(queryset, uuid)))


RESEND_COOLDOWN = 30  # seconds; a mailbox is not a place to fire repeatedly


class EmailLogResendView(APIView):
    """Send a logged message again: same text, same recipient, through the
    clinic's mail server as it is configured now."""

    permission_classes = [IsClinicAdmin]

    def post(self, request, uuid):
        queryset = scope_queryset_to_user(EmailLog.objects.all(), request.user)
        entry = _one(queryset, uuid)
        if entry.kind not in RESENDABLE:
            raise ValidationError({
                "detail": "هذا النوع لا يُعاد إرساله: يحمل رمز دخول أو رابطاً لمرة واحدة. أصدر رمزاً أو دعوة جديدة.",
            })
        root = entry.resent_from or entry
        tenant = request.user.tenant
        connection, sender = sender_for(branch=entry.branch, customer=tenant)
        if connection is None:
            return Response({"detail": "لم يُضبط خادم البريد بعد. اضبطه من «البريد الإلكتروني»."}, status=503)
        key = f"email-resend:{root.uuid}"
        if not cache.add(key, 1, RESEND_COOLDOWN):
            return Response({"detail": "أُعيد إرسال هذه الرسالة قبل لحظات. انتظر قليلاً ثم أعد المحاولة."}, status=429)

        sent = deliver(
            kind=entry.kind, tenant=tenant, branch=entry.branch, to=entry.to_address, subject=entry.subject,
            body=entry.body, html=entry.is_html, template=entry.template,
            connection=connection, sender=sender, resent_from=root,
        )
        AuditLog.objects.create(
            tenant=tenant, user=request.user, action="custom", model_name="EmailLog", object_id=str(root.pk),
            description=f"email re-sent: {entry.kind} to {entry.to_address} ({'sent' if sent else 'failed'})",
            ip_address=request.META.get("REMOTE_ADDR"), user_agent=request.META.get("HTTP_USER_AGENT"),
        )
        if not sent:
            cache.delete(key)
            return Response({"detail": "تعذّر إرسال الرسالة الآن. حاول لاحقاً."}, status=502)
        return Response(_detail(_one(queryset, uuid)))


class PlatformEmailLogListView(APIView):
    permission_classes = [IsPlatformStaff]

    def get(self, request, uuid):
        tenant = get_object_or_404(Tenant, uuid=uuid)
        with tenant_context(tenant):
            response = _list(request, EmailLog.objects.all())
        record(request, tenant, "inspect", f"viewed the email log of {tenant.slug}",
               model_name="EmailLog", object_id=tenant.pk)
        return response


class PlatformEmailLogDetailView(APIView):
    permission_classes = [IsPlatformStaff]

    def get(self, request, uuid, log_uuid):
        tenant = get_object_or_404(Tenant, uuid=uuid)
        with tenant_context(tenant):
            data = _detail(_one(EmailLog.objects.all(), log_uuid))
        record(request, tenant, "inspect", f"opened an email of {tenant.slug}",
               model_name="EmailLog", object_id=log_uuid)
        return Response(data)
