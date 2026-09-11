"""Asking to open a clinic group — the public form and the developer's queue
(docs/06 PLAT-003).

* `GET /api/signup/options/`, `POST /api/signup/`: public, throttled, with a
  honeypot field. A request is only a request: nothing is created until the
  developer approves it.
* `/api/platform/signups/…`: the queue. Approving onboards the group through
  the same path as the portal's own form (platform_admin/onboarding.py), sets
  the requested plan and billing cycle, and — if asked — emails the owner
  their sign-in; rejecting records and emails the reason. All audited.
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from platform_admin import billing, notices
from platform_admin.audit import record
from platform_admin.models import CommercialTerms, SignupRequest
from platform_admin.onboarding import clean, onboard
from subscriptions.entitlements import FEATURES, LIMITS
from subscriptions.models import Plan
from tenants.models import Tenant

from .platform import IsPlatformStaff, tenant_summary

User = get_user_model()
TEXT_LIMITS = {"group_name": 150, "clinic_name": 150, "owner_name": 150, "phone": 32, "city": 80, "specialty": 120}


class SignupThrottle(AnonRateThrottle):
    scope = "signup"


def public_plans():
    from api.views.subscription import FEATURE_LABELS

    return [
        {
            "code": plan.code,
            "name": plan.name,
            "description": plan.description,
            "price": str(plan.price),
            "currency": plan.currency,
            "billing_period": plan.billing_period,
            "billing_period_label": plan.get_billing_period_display(),
            "limits": plan.limits,
            "features": [FEATURE_LABELS.get(key, FEATURES[key][0]) for key, on in (plan.features or {}).items()
                         if on and key in FEATURES],
        }
        for plan in Plan.objects.filter(is_active=True, is_public=True).order_by("price")
    ]


class SignupOptionsView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({
            "plans": public_plans(),
            "cycles": [{"value": v, "label": label} for v, label in CommercialTerms.Cycle.choices],
            "limits": {key: label for key, label in LIMITS.items()},
        })


class SignupView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = [SignupThrottle]

    def post(self, request):
        data = request.data
        # A field people never see; bots fill every field they find.
        if str(data.get("website") or "").strip():
            return Response({"ok": True}, status=status.HTTP_201_CREATED)
        errors = {}
        values = {name: str(data.get(name) or "").strip()[:limit] for name, limit in TEXT_LIMITS.items()}
        for required, message in (("group_name", "اسم المجموعة أو العيادة مطلوب."),
                                  ("owner_name", "اسم المالك مطلوب."), ("phone", "رقم الهاتف مطلوب.")):
            if not values[required]:
                errors[required] = [message]
        email = str(data.get("email") or "").strip().lower()
        try:
            validate_email(email)
        except ValidationError:
            errors["email"] = ["بريد إلكتروني غير صالح."]
        else:
            if User.objects.filter(email__iexact=email).exists():
                errors["email"] = ["هذا البريد مسجل بالفعل. سجّل الدخول أو استخدم بريداً آخر."]
            elif SignupRequest.objects.filter(email__iexact=email, status=SignupRequest.Status.PENDING).exists():
                errors["email"] = ["لديك طلب قيد المراجعة بالفعل؛ سنتواصل معك قريباً."]
        plan = None
        if data.get("plan"):
            plan = Plan.objects.filter(code=data["plan"], is_active=True, is_public=True).first()
            if plan is None:
                errors["plan"] = ["باقة غير متاحة."]
        cycle = data.get("cycle") or CommercialTerms.Cycle.MONTHLY
        if cycle not in CommercialTerms.Cycle.values:
            errors["cycle"] = ["الدورة: شهري أو سنوي."]
        counts = {}
        for name in ("branches", "doctors"):
            try:
                counts[name] = min(max(int(data.get(name) or 1), 1), 999)
            except (TypeError, ValueError):
                errors[name] = ["رقم صحيح."]
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        signup = SignupRequest.objects.create(
            **values, **counts, email=email, plan=plan, cycle=cycle,
            message=str(data.get("message") or "").strip()[:2000],
            ip_address=request.META.get("REMOTE_ADDR"),
        )
        notices.send(email, "استلمنا طلب فتح العيادة", [
            f"أهلاً {signup.owner_name}،",
            "",
            f"استلمنا طلبك لفتح «{signup.group_name}» على المنصة، وسنراجعه ونتواصل معك قريباً.",
        ])
        notices.send(notices.operators(), f"طلب عيادة جديد: {signup.group_name}", [
            f"المجموعة: {signup.group_name}",
            f"المالك: {signup.owner_name} — {signup.email} — {signup.phone}",
            f"الباقة: {plan.name if plan else 'لم يحدد'} ({signup.get_cycle_display()})",
            f"العيادات: {signup.branches} · الأطباء: {signup.doctors}",
            "",
            signup.message,
        ])
        return Response({"ok": True}, status=status.HTTP_201_CREATED)


# ------------------------------------------------------------------ the queue


def signup_payload(signup):
    return {
        "id": signup.pk,
        "group_name": signup.group_name,
        "clinic_name": signup.clinic_name,
        "owner_name": signup.owner_name,
        "email": signup.email,
        "phone": signup.phone,
        "city": signup.city,
        "specialty": signup.specialty,
        "branches": signup.branches,
        "doctors": signup.doctors,
        "plan": signup.plan.code if signup.plan_id else None,
        "plan_name": signup.plan.name if signup.plan_id else None,
        "cycle": signup.cycle,
        "cycle_label": signup.get_cycle_display(),
        "message": signup.message,
        "status": signup.status,
        "status_label": signup.get_status_display(),
        "reject_reason": signup.reject_reason,
        "tenant": str(signup.customer.uuid) if signup.customer_id else None,
        "handled_by": getattr(signup.handled_by, "email", None),
        "handled_at": signup.handled_at,
        "created_at": signup.created_at,
    }


class SignupQueueView(APIView):
    permission_classes = [IsPlatformStaff]

    def get(self, request):
        rows = SignupRequest.objects.select_related("plan", "customer", "handled_by")
        wanted = request.query_params.get("status")
        if wanted:
            rows = rows.filter(status=wanted)
        counts = {value: 0 for value in SignupRequest.Status.values}
        for value in SignupRequest.objects.values_list("status", flat=True):
            counts[value] += 1
        return Response({"items": [signup_payload(s) for s in rows[:500]], "counts": counts})


class SignupApproveView(APIView):
    permission_classes = [IsPlatformStaff]

    def post(self, request, pk):
        data = request.data
        with transaction.atomic():
            signup = get_object_or_404(SignupRequest.objects.select_for_update(), pk=pk)
            if signup.status != SignupRequest.Status.PENDING:
                return Response({"detail": "هذا الطلب تمت معالجته بالفعل."}, status=400)
            values, errors = clean({
                "name": data.get("name") or signup.group_name,
                "slug": data.get("slug"),
                "admin_email": signup.email,
                "branch_name": data.get("branch_name") or signup.clinic_name or "الفرع الرئيسي",
                "branch_code": data.get("branch_code"),
                "status": data.get("status") or Tenant.Status.TRIAL,
            })
            plan = signup.plan
            if data.get("plan"):
                plan = Plan.objects.filter(code=data["plan"]).first()
                if plan is None:
                    errors["plan"] = ["باقة غير موجودة."]
            cycle = data.get("cycle") or signup.cycle
            if cycle not in CommercialTerms.Cycle.values:
                errors["cycle"] = ["الدورة: شهري أو سنوي."]
            if errors:
                return Response(errors, status=400)
            tenant, owner, password = onboard(values, plan=plan)
            terms = billing.terms_for(tenant)
            terms.cycle = cycle
            terms.notes = f"من طلب التسجيل #{signup.pk}"
            terms.save(update_fields=["cycle", "notes"])
            signup.status = SignupRequest.Status.APPROVED
            signup.customer = tenant
            signup.handled_by = request.user
            signup.handled_at = timezone.now()
            signup.save(update_fields=["status", "customer", "handled_by", "handled_at"])
            record(
                request, tenant, "signup approved",
                f"request #{signup.pk}: created {tenant.slug} with owner {owner.email}",
                model_name="SignupRequest", object_id=signup.pk,
            )
        emailed = False
        if data.get("send_email", True):
            emailed = notices.send(signup.email, "تم فتح حساب عيادتك", [
                f"أهلاً {signup.owner_name}،",
                "",
                f"تمت الموافقة على طلبك وفُتح حساب «{tenant.name}».",
                f"رابط الدخول: {request.build_absolute_uri('/app/login')}",
                f"البريد: {owner.email}",
                f"كلمة المرور المؤقتة: {password}",
                "",
                "غيّر كلمة المرور بعد أول دخول من صفحة «حسابي».",
            ])
        response = Response({
            "request": signup_payload(signup),
            "tenant": tenant_summary(tenant),
            "admin_email": owner.email,
            "admin_password": password,
            "emailed": emailed,
        }, status=201)
        response["Cache-Control"] = "no-store"
        return response


class SignupRejectView(APIView):
    permission_classes = [IsPlatformStaff]

    def post(self, request, pk):
        reason = str(request.data.get("reason") or "").strip()[:300]
        if not reason:
            return Response({"detail": "اكتب سبب الرفض."}, status=400)
        with transaction.atomic():
            signup = get_object_or_404(SignupRequest.objects.select_for_update(), pk=pk)
            if signup.status != SignupRequest.Status.PENDING:
                return Response({"detail": "هذا الطلب تمت معالجته بالفعل."}, status=400)
            signup.status = SignupRequest.Status.REJECTED
            signup.reject_reason = reason
            signup.handled_by = request.user
            signup.handled_at = timezone.now()
            signup.save(update_fields=["status", "reject_reason", "handled_by", "handled_at"])
            record(request, None, "signup rejected", f"request #{signup.pk} ({signup.email}): {reason}",
                   model_name="SignupRequest", object_id=signup.pk)
        if request.data.get("send_email", True):
            notices.send(signup.email, "بخصوص طلب فتح العيادة", [
                f"أهلاً {signup.owner_name}،",
                "",
                f"نعتذر، لم نتمكن من قبول طلب «{signup.group_name}» حالياً.",
                f"السبب: {reason}",
            ])
        return Response(signup_payload(signup))
