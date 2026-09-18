"""`POST /api/my-report/email/` — send the signed-in person their own report.

Body: `{"from": "YYYY-MM-DD", "to": "YYYY-MM-DD"}` (both optional; today).
The recipient is never taken from the request: it is the person's own address
(reports.personal.recipient). See that module for what each role receives.
"""

from datetime import timedelta

from django.core.cache import cache
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.roles import display_name
from api.permissions import IsClinicMember
from platform_admin.mailer import sender_for
from reports import personal

MAX_DAYS = 366
COOLDOWN_SECONDS = 30


def _mask(address):
    name, _, domain = address.partition("@")
    return f"{name[:2]}***@{domain}"


class MyReportEmailView(APIView):
    permission_classes = [IsClinicMember]

    def post(self, request):
        user = request.user
        start = parse_date(str(request.data.get("from") or "")) or timezone.now().date()
        end = parse_date(str(request.data.get("to") or "")) or start
        if end < start or (end - start) > timedelta(days=MAX_DAYS):
            return Response({"detail": "الفترة غير صالحة."}, status=400)
        to = personal.recipient(user)
        if not to:
            return Response({"detail": "لا يوجد بريد إلكتروني مسجّل لحسابك."}, status=400)

        tenant = user.tenant
        branch = user.branch if getattr(user, "branch_id", None) else None
        connection, sender = sender_for(branch=branch, customer=tenant)
        if connection is None:
            return Response({"detail": "لم يُضبط خادم البريد بعد. تواصل مع إدارة النظام."}, status=503)

        # A mailbox is not a place to fire repeatedly.
        key = f"my-report:{user.pk}"
        if not cache.add(key, 1, COOLDOWN_SECONDS):
            return Response({"detail": "أُرسل تقرير قبل لحظات. انتظر قليلاً ثم أعد المحاولة."}, status=429)

        title, sections = personal.build(user, start, end)
        period = f"{start:%Y-%m-%d}" if start == end else f"{start:%Y-%m-%d} → {end:%Y-%m-%d}"
        html = render_to_string("reports/personal_report.html", {
            "title": title, "name": display_name(user), "clinic": getattr(tenant, "name", ""),
            "period": period, "sections": sections,
        })
        message = EmailMessage(f"{title} — {period}", html, from_email=sender, to=[to], connection=connection)
        message.content_subtype = "html"
        try:
            message.send()
        except Exception:  # noqa: BLE001 — an unreachable mail server is reported, not a crash
            cache.delete(key)
            return Response({"detail": "تعذّر إرسال البريد الآن. حاول لاحقاً."}, status=502)
        return Response({"sent_to": _mask(to)})
