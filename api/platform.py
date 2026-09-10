"""The owner portal's API — the platform operator's view of every clinic.

A second front door onto `platform_admin`, so it carries that app's rules
unchanged rather than a looser copy of them (see platform_admin/permissions.py):

* **Gate.** `is_platform_staff` — the flag, AND no tenant of one's own. Not
  `is_superuser`.
* **One tenant at a time.** Cross-tenant reach is entering one clinic's
  `tenant_context` on the ordinary connection for the duration of one read. No
  privileged connection, no BYPASSRLS, and `TenantMiddleware` is untouched.
* **Clinical data is never written.** The only tenant-owned write is moving a
  subscription between plans. Suspending a clinic writes to `Tenant`, a platform
  model with no isolation policy.
* **Audited.** Opening a clinic's record is written to *that clinic's* audit
  trail, as are status and plan changes and onboarding — the audit is the
  control, so failures propagate.

Onboarding mirrors `manage.py create_tenant` step for step: same validation,
same provisioning, one transaction, and a generated password shown once.
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email, validate_slug
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils.text import slugify
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from appointments.models import Appointment
from billing.models import Payment
from medical.models import Visit
from platform_admin.audit import record
from platform_admin.permissions import is_platform_staff
from subscriptions.entitlements import current_subscription, resolve_features
from subscriptions.models import Plan, Subscription
from subscriptions.usage import limits_table, usage_for
from tenants.context import tenant_context
from tenants.models import Tenant
from tenants.provisioning import (
    create_first_branch,
    create_tenant_admin,
    provision_tenant_defaults,
)

User = get_user_model()


class IsPlatformStaff(permissions.BasePermission):
    message = "هذه الصفحة مقصورة على مشغّلي المنصة."

    def has_permission(self, request, view):
        return is_platform_staff(request.user)


def plan_data(plan):
    if plan is None:
        return None
    return {
        "code": plan.code,
        "name": plan.name,
        "price": plan.price,
        "currency": plan.currency,
        "billing_period": plan.get_billing_period_display(),
    }


def tenant_summary(tenant):
    """One clinic's row. Read inside its own context — a join across tenant
    tables on an unbound connection returns nothing and would look like a
    platform with no data."""
    with tenant_context(tenant):
        subscription = current_subscription(tenant)
        usage = usage_for(tenant)
    return {
        "uuid": str(tenant.uuid),
        "name": tenant.name,
        "slug": tenant.slug,
        "status": tenant.status,
        "status_label": tenant.get_status_display(),
        "created_at": tenant.created_at,
        "plan": plan_data(subscription.plan if subscription else None),
        "trial_ends_on": subscription.trial_ends_on if subscription else None,
        "ends_on": subscription.ends_on if subscription else None,
        "patients": usage["max_patients"],
        "staff": usage["max_staff"],
        "branches": usage["max_branches"],
    }


class PlanListView(APIView):
    permission_classes = [IsPlatformStaff]

    def get(self, request):
        return Response([
            {**plan_data(plan), "id": plan.pk}
            for plan in Plan.objects.filter(is_active=True).order_by("price")
        ])


class TenantListView(APIView):
    permission_classes = [IsPlatformStaff]

    def get(self, request):
        rows = [tenant_summary(tenant) for tenant in Tenant.objects.all()]
        by_status = {}
        for row in rows:
            by_status[row["status"]] = by_status.get(row["status"], 0) + 1
        return Response({
            "results": rows,
            "totals": {
                "tenants": len(rows),
                "by_status": by_status,
                "patients": sum(row["patients"] for row in rows),
            },
            "statuses": [{"value": v, "label": l} for v, l in Tenant.Status.choices],
        })

    def post(self, request):
        """Onboard a clinic — `manage.py create_tenant`, from the screen."""
        data = request.data
        errors = {}

        name = (data.get("name") or "").strip()
        slug = (data.get("slug") or slugify(name)).strip().lower()
        email = (data.get("admin_email") or "").strip().lower()
        branch_name = (data.get("branch_name") or "الفرع الرئيسي").strip()
        branch_code = (data.get("branch_code") or "MAIN").strip().upper()[:20]
        tenant_status = data.get("status") or Tenant.Status.TRIAL

        if not name:
            errors["name"] = ["اسم العيادة مطلوب."]
        if not slug:
            # slugify() returns "" for Arabic, and a blank slug is unusable.
            errors["slug"] = ["أدخل معرّفاً لاتينياً للعيادة (مثال: dr-ahmed)."]
        else:
            try:
                validate_slug(slug)
            except DjangoValidationError:
                errors["slug"] = ["المعرّف يقبل حروفاً لاتينية وأرقاماً و - فقط."]
            if Tenant.objects.filter(slug=slug).exists():
                errors["slug"] = ["يوجد عيادة بهذا المعرّف بالفعل."]
        try:
            validate_email(email)
        except DjangoValidationError:
            errors["admin_email"] = ["بريد إلكتروني غير صالح."]
        else:
            if User.objects.filter(email__iexact=email).exists():
                errors["admin_email"] = ["هذا البريد مستخدم بالفعل."]
        if tenant_status not in dict(Tenant.Status.choices):
            errors["status"] = ["حالة غير صالحة."]
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            tenant = Tenant.objects.create(name=name, slug=slug, status=tenant_status)
            provision_tenant_defaults(tenant)
            branch = create_first_branch(tenant, branch_name, branch_code)
            admin, password = create_tenant_admin(
                tenant, email=email, username="admin", branch=branch
            )
            record(
                request, tenant, "onboard",
                f"created {tenant.slug} with administrator {admin.email}",
                model_name="Tenant", object_id=tenant.pk,
            )

        response = Response(
            {
                "tenant": tenant_summary(tenant),
                "admin_email": admin.email,
                # Shown once, never stored readable — the same contract as the
                # command, which prints it once.
                "admin_password": password,
            },
            status=status.HTTP_201_CREATED,
        )
        response["Cache-Control"] = "no-store"
        return response


class TenantDetailView(APIView):
    permission_classes = [IsPlatformStaff]

    def get(self, request, uuid):
        tenant = get_object_or_404(Tenant, uuid=uuid)
        with tenant_context(tenant):
            subscription = current_subscription(tenant)
            usage = usage_for(tenant)
            snapshot = {
                "appointments": Appointment.objects.count(),
                "visits": Visit.objects.count(),
                "revenue": Payment.objects.aggregate(total=Sum("amount"))["total"] or 0,
            }
            history = [
                {
                    "plan": sub.plan.name,
                    "status": sub.get_status_display(),
                    "started_on": sub.started_on,
                    "ends_on": sub.ends_on,
                }
                for sub in Subscription.objects.select_related("plan").all()[:20]
            ]
            features = resolve_features(tenant)

        # The sensitive act is a platform operator looking at a clinic at all.
        record(
            request, tenant, "inspect",
            f"viewed the platform overview for {tenant.slug}",
            model_name="Tenant", object_id=tenant.pk,
        )

        return Response({
            **tenant_summary(tenant),
            "subscription_status": subscription.get_status_display() if subscription else None,
            "limits": limits_table(tenant, subscription, usage),
            "snapshot": snapshot,
            "history": history,
            "features": [{"key": k, "enabled": bool(v)} for k, v in sorted(features.items())],
        })


class TenantStatusView(APIView):
    """Approve, suspend, activate — a write to `Tenant`, not to clinic data."""

    permission_classes = [IsPlatformStaff]

    def post(self, request, uuid):
        tenant = get_object_or_404(Tenant, uuid=uuid)
        new_status = request.data.get("status")
        if new_status not in dict(Tenant.Status.choices):
            return Response({"status": ["حالة غير صالحة."]}, status=400)
        previous = tenant.status
        if previous != new_status:
            tenant.status = new_status
            tenant.save(update_fields=["status"])
            record(
                request, tenant, "tenant status",
                f"{tenant.slug}: {previous} -> {new_status}",
                model_name="Tenant", object_id=tenant.pk,
            )
        return Response(tenant_summary(tenant))


class TenantPlanView(APIView):
    """The only tenant-owned write available to the platform: the plan."""

    permission_classes = [IsPlatformStaff]

    def post(self, request, uuid):
        tenant = get_object_or_404(Tenant, uuid=uuid)
        plan = Plan.objects.filter(code=request.data.get("plan"), is_active=True).first()
        if plan is None:
            return Response({"plan": ["باقة غير موجودة."]}, status=400)
        with tenant_context(tenant):
            subscription = current_subscription(tenant)
            if subscription is None:
                return Response({"detail": "لا يوجد اشتراك نشط لهذه العيادة."}, status=400)
            previous = subscription.plan
            if previous.pk != plan.pk:
                subscription.plan = plan
                subscription.save(update_fields=["plan", "updated_at"])
        if previous.pk != plan.pk:
            record(
                request, tenant, "plan change",
                f"{tenant.slug}: {previous.code} -> {plan.code}",
                model_name="Subscription", object_id=subscription.pk,
            )
        return Response(tenant_summary(tenant))
