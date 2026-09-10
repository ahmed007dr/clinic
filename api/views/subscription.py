"""The clinic's own plan, limits and usage (FE-026 / WIRE-007).

Read-only, Admin-only, and derived from `request.user.tenant` alone — never a
URL parameter. Seeing *another* clinic's subscription is the owner portal's
job and stays there.
"""

from rest_framework.response import Response
from rest_framework.views import APIView

from api.permissions import IsGroupOwner
from subscriptions.entitlements import current_subscription, resolve_features
from subscriptions.usage import limits_table
from tenants.context import get_current_tenant

FEATURE_LABELS = {
    "reports": "التقارير الدورية بالبريد",
    "whatsapp": "رسائل واتساب",
    "online_payments": "الدفع الإلكتروني",
    "advanced_analytics": "تحليلات متقدمة",
    "ai": "مساعد ذكي",
    "packages": "باقات العلاج",
}


#: Features a plan can carry but the system does not implement yet
#: (docs/11, WIRE-005/006). Kept here, next to the labels, so adding the
#: implementation and removing the entry happen in the same change.
NOT_YET_BUILT = {
    "whatsapp",          # PLAT-004 — no provider chosen
    "online_payments",   # FIN-004/005 — no gateway
    "advanced_analytics",
    "ai",
    "reports",           # generators exist; nothing schedules them (WIRE-006)
}


class SubscriptionView(APIView):
    permission_classes = [IsGroupOwner]

    def get(self, request):
        tenant = get_current_tenant()
        subscription = current_subscription(tenant)
        plan = subscription.plan if subscription else None
        return Response({
            "clinic": tenant.name,
            "clinic_status": tenant.status,
            "clinic_status_label": tenant.get_status_display(),
            "plan": {
                "name": plan.name,
                "code": plan.code,
                "price": plan.price,
                "currency": plan.currency,
                "billing_period": plan.get_billing_period_display(),
            } if plan else None,
            "subscription": {
                "status": subscription.status,
                "status_label": subscription.get_status_display(),
                "started_on": subscription.started_on,
                "ends_on": subscription.ends_on,
                "trial_ends_on": subscription.trial_ends_on,
            } if subscription else None,
            "limits": limits_table(tenant, subscription),
            "features": [
                {
                    "key": key,
                    "label": FEATURE_LABELS.get(key, key),
                    "enabled": bool(enabled),
                    # A plan can grant a feature the system does not have yet.
                    # Telling a clinic "WhatsApp: enabled" when nothing sends
                    # WhatsApp is a promise the product breaks — so those are
                    # reported as coming, whatever the plan says.
                    "available": key not in NOT_YET_BUILT,
                }
                for key, enabled in sorted(resolve_features(tenant).items())
            ],
        })
