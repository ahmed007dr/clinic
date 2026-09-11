"""The developer portal's full control over groups (docs/06 PLAT-004).

The group owner's decision (2026-09-11): the platform has full control over
every group and its owners — edit the group, manage its accounts (reset a
password, stop or restart an account, sign it out everywhere, add another
owner), stop or restart a clinic, switch services on or off and change limits
beyond the plan, set the subscription's dates, and sign in as an account for
support (platform_admin/impersonation.py), which is also how medical records
are reached and corrected.

Full administrators only for every change (`IsPlatformStaff`); every change
is written to the group's audit trail.
"""

from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError
from django.core.validators import validate_email, validate_slug
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.dateparse import parse_date
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from branches.models import Branch
from platform_admin import impersonation
from platform_admin.audit import record
from platform_admin.models import SupportSession
from subscriptions.entitlements import FEATURES, LIMITS, current_subscription, resolve_features
from subscriptions.models import Subscription
from tenants.context import tenant_context
from tenants.models import Tenant
from tenants.provisioning import PASSWORD_ALPHABET

from .platform import IsPlatformStaff, tenant_summary

User = get_user_model()


def _error(message, code=400):
    return Response({"detail": str(message)}, status=code)


def _tenant(uuid):
    return get_object_or_404(Tenant, uuid=uuid)


def _account(uuid):
    """A clinic account — never a platform operator's."""
    return get_object_or_404(User, uuid=uuid, tenant__isnull=False)


def end_sessions(user):
    """Sign `user` out on every device (database sessions)."""
    ended = 0
    for session in Session.objects.filter(expire_date__gte=timezone.now()).iterator():
        if session.get_decoded().get("_auth_user_id") == str(user.pk):
            session.delete()
            ended += 1
    return ended


def new_password():
    return get_random_string(14, allowed_chars=PASSWORD_ALPHABET)


# ------------------------------------------------------------------ the group


class TenantEditView(APIView):
    """PATCH the group's name, its patient-portal link (slug) and portal
    switches."""

    permission_classes = [IsPlatformStaff]

    def patch(self, request, uuid):
        tenant = _tenant(uuid)
        data = request.data
        changed = []
        if "name" in data:
            name = str(data["name"] or "").strip()
            if not name:
                return _error("الاسم مطلوب.")
            if name != tenant.name:
                tenant.name = name[:200]
                changed.append("name")
        if "slug" in data and data["slug"] != tenant.slug:
            slug = str(data["slug"] or "").strip().lower()
            try:
                validate_slug(slug)
            except ValidationError:
                return _error("المعرّف يقبل حروفاً لاتينية وأرقاماً و - فقط.")
            if Tenant.objects.filter(slug=slug).exclude(pk=tenant.pk).exists():
                return _error("يوجد مجموعة بهذا المعرّف.")
            changed.append(f"slug {tenant.slug}->{slug}")
            tenant.slug = slug
        for flag in ("portal_show_diagnosis", "portal_self_registration"):
            if flag in data and bool(data[flag]) != getattr(tenant, flag):
                setattr(tenant, flag, bool(data[flag]))
                changed.append(flag)
        if changed:
            tenant.save()
            record(request, tenant, "group edited", ", ".join(changed), model_name="Tenant", object_id=tenant.pk)
        return Response(tenant_summary(tenant))


class TenantOwnerView(APIView):
    """POST {email, username?}: add another owner account to the group."""

    permission_classes = [IsPlatformStaff]

    def post(self, request, uuid):
        from accounts.models import ClinicRole

        tenant = _tenant(uuid)
        email = str(request.data.get("email") or "").strip().lower()
        try:
            validate_email(email)
        except ValidationError:
            return _error("بريد إلكتروني غير صالح.")
        if User.objects.filter(email__iexact=email).exists():
            return _error("هذا البريد مستخدم بالفعل.")
        username = str(request.data.get("username") or email.split("@")[0]).strip()[:150]
        password = new_password()
        with transaction.atomic(), tenant_context(tenant):
            if User.objects.filter(tenant=tenant, username=username).exists():
                return _error("اسم المستخدم مستخدم في هذه المجموعة.")
            role = ClinicRole.all_objects.get(tenant=tenant, name="Owner")
            branch = Branch.all_objects.filter(tenant=tenant).order_by("pk").first()
            owner = User.objects.create_user(
                username=username, email=email, password=password, tenant=tenant, role=role, branch=branch,
                clinic_code=tenant.slug.upper()[:20],
            )
            record(request, tenant, "owner added", owner.email, model_name="User", object_id=owner.pk)
        response = Response({"email": owner.email, "username": owner.username, "password": password}, status=201)
        response["Cache-Control"] = "no-store"
        return response


class TenantBranchActiveView(APIView):
    """POST {active}: stop or restart one clinic of the group. A stopped
    clinic's staff are shut out at once (TenantMiddleware)."""

    permission_classes = [IsPlatformStaff]

    def post(self, request, uuid, pk):
        tenant = _tenant(uuid)
        active = bool(request.data.get("active"))
        with tenant_context(tenant):
            branch = get_object_or_404(Branch.all_objects, pk=pk, tenant=tenant)
            if branch.is_active != active:
                branch.is_active = active
                branch.save(update_fields=["is_active"])
                record(request, tenant, "clinic " + ("restarted" if active else "stopped"), branch.name,
                       model_name="Branch", object_id=branch.pk)
            return Response({"id": branch.pk, "name": branch.name, "is_active": branch.is_active})


# ------------------------------------------------------------------ accounts


class AccountActionView(APIView):
    """POST reset-password | activate | deactivate | logout on one account."""

    permission_classes = [IsPlatformStaff]
    ACTIONS = ("reset-password", "activate", "deactivate", "logout")

    def post(self, request, uuid, action):
        if action not in self.ACTIONS:
            return _error("إجراء غير معروف.", 404)
        user = _account(uuid)
        tenant = user.tenant
        body = {"uuid": str(user.uuid), "username": user.username}
        if action == "reset-password":
            password = new_password()
            user.set_password(password)
            user.save(update_fields=["password"])
            body["ended_sessions"] = end_sessions(user)
            body["password"] = password
        elif action in ("activate", "deactivate"):
            user.is_active = action == "activate"
            user.save(update_fields=["is_active"])
            if not user.is_active:
                body["ended_sessions"] = end_sessions(user)
        else:
            body["ended_sessions"] = end_sessions(user)
        body["is_active"] = user.is_active
        record(request, tenant, f"account {action}", user.username, model_name="User", object_id=user.pk)
        response = Response(body)
        response["Cache-Control"] = "no-store"
        return response


# ------------------------------------------------------------------ services and limits


def entitlements_of(tenant):
    from api.views.subscription import FEATURE_LABELS, NOT_YET_BUILT
    from subscriptions.usage import limits_table

    with tenant_context(tenant):
        subscription = current_subscription(tenant)
        resolved = resolve_features(tenant)
        rows = limits_table(tenant, subscription)
        latest = subscription or Subscription.all_objects.filter(tenant=tenant).order_by("-started_on", "-id").first()
    plan = subscription.plan if subscription else None
    overrides = (subscription.feature_overrides or {}) if subscription else {}
    limit_overrides = (subscription.limit_overrides or {}) if subscription else {}
    return {
        "subscription": {
            "id": latest.pk,
            "plan": latest.plan.name,
            "status": latest.status,
            "status_label": latest.get_status_display(),
            "started_on": latest.started_on,
            "ends_on": latest.ends_on,
            "trial_ends_on": latest.trial_ends_on,
            "notes": latest.notes,
        } if latest else None,
        "statuses": [{"value": v, "label": label} for v, label in Subscription.Status.choices],
        "features": [
            {
                "key": key,
                "label": FEATURE_LABELS.get(key, label),
                "in_plan": bool((plan.features or {}).get(key, default)) if plan else False,
                "override": overrides.get(key),
                "enabled": bool(resolved.get(key)),
                "built": key not in NOT_YET_BUILT,
            }
            for key, (label, default) in FEATURES.items()
        ],
        "limits": [
            {**row, "plan_value": getattr(plan, row["key"]) if plan else None,
             "overridden": row["key"] in limit_overrides}
            for row in rows
        ],
    }


class EntitlementsView(APIView):
    """GET what the group may use and why; PATCH to switch services on or
    off (`features: {key: true|false|null}`, null = back to the plan), change
    limits (`limits: {key: number|"unlimited"|null}`) and the subscription's
    status and dates."""

    permission_classes = [IsPlatformStaff]

    def get(self, request, uuid):
        return Response(entitlements_of(_tenant(uuid)))

    def patch(self, request, uuid):
        tenant = _tenant(uuid)
        data = request.data
        with transaction.atomic(), tenant_context(tenant):
            subscription = current_subscription(tenant) or Subscription.all_objects.filter(
                tenant=tenant).order_by("-started_on", "-id").first()
            if subscription is None:
                return _error("لا يوجد اشتراك لهذه المجموعة.")
            changes = []
            features = dict(subscription.feature_overrides or {})
            for key, value in (data.get("features") or {}).items():
                if key not in FEATURES:
                    return _error(f"خدمة غير معروفة: {key}")
                if value is None:
                    features.pop(key, None)
                else:
                    features[key] = bool(value)
                changes.append(f"feature {key}={value}")
            limits = dict(subscription.limit_overrides or {})
            for key, value in (data.get("limits") or {}).items():
                if key not in LIMITS:
                    return _error(f"حد غير معروف: {key}")
                if value is None or value == "":
                    limits.pop(key, None)
                elif value == "unlimited":
                    limits[key] = None
                else:
                    try:
                        limits[key] = max(int(value), 0)
                    except (TypeError, ValueError):
                        return _error("الحدود أرقام صحيحة.")
                changes.append(f"limit {key}={value}")
            subscription.feature_overrides = features
            subscription.limit_overrides = limits
            fields = ["feature_overrides", "limit_overrides", "updated_at"]
            if data.get("status"):
                if data["status"] not in Subscription.Status.values:
                    return _error("حالة اشتراك غير صالحة.")
                if data["status"] == "active" and subscription.status != "active":
                    # One active subscription per group: retire the others.
                    Subscription.all_objects.filter(tenant=tenant, status="active").exclude(
                        pk=subscription.pk).update(status="cancelled")
                subscription.status = data["status"]
                fields.append("status")
                changes.append(f"status {subscription.status}")
            for name in ("ends_on", "trial_ends_on"):
                if name in data:
                    value = parse_date(str(data[name])) if data[name] else None
                    if data[name] and value is None:
                        return _error("تاريخ غير صالح.")
                    setattr(subscription, name, value)
                    fields.append(name)
                    changes.append(f"{name} {value or '-'}")
            if subscription.ends_on and subscription.ends_on < subscription.started_on:
                return _error("تاريخ الانتهاء قبل البداية.")
            subscription.save(update_fields=fields)
        if changes:
            record(request, tenant, "services and limits", "; ".join(changes), model_name="Subscription",
                   object_id=subscription.pk)
        return Response(entitlements_of(tenant))


# ------------------------------------------------------------------ support ("login as")


def support_payload(row):
    return {
        "id": row.pk,
        "operator": row.operator.email,
        "target": row.target.username,
        "reason": row.reason,
        "started_at": row.started_at,
        "expires_at": row.expires_at,
        "ended_at": row.ended_at,
        "active": row.ended_at is None and row.expires_at > timezone.now(),
    }


class SupportStartView(APIView):
    """GET the group's support sessions; POST {user, minutes, reason} to sign
    in as one of its accounts."""

    permission_classes = [IsPlatformStaff]

    def get(self, request, uuid):
        tenant = _tenant(uuid)
        rows = SupportSession.objects.filter(customer=tenant).select_related("operator", "target")[:50]
        return Response([support_payload(row) for row in rows])

    def post(self, request, uuid):
        tenant = _tenant(uuid)
        target = get_object_or_404(User, uuid=request.data.get("user"), tenant=tenant)
        operator = request.user

        def audit(log):
            # Before the sign-in switches request.user: filed under the operator.
            record(
                request, tenant, "support login",
                f"{operator.email} as {target.username} until {log.expires_at:%Y-%m-%d %H:%M}: {log.reason}",
                model_name="SupportSession", object_id=log.pk,
            )

        try:
            with transaction.atomic():
                log = impersonation.start(
                    request, target, request.data.get("reason"), request.data.get("minutes", 30), before_login=audit,
                )
        except impersonation.SupportError as error:
            return _error(error)
        return Response({"redirect": "/app/", "expires_at": log.expires_at}, status=201)


class SupportEndView(APIView):
    """End a support session and return to the portal."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        try:
            operator = impersonation.end(request)
        except impersonation.SupportError as error:
            return _error(error)
        return Response({"redirect": "/app/platform" if operator else "/app/platform/login"})

