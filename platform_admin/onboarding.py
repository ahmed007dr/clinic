"""Opening a new owner group — one path for every door.

`manage.py create_tenant`, the portal's "new group" form and approving a
signup request all end here: the same validation, the same provisioning
(tenants/provisioning.py), one transaction, and a generated owner password
returned once.
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import validate_email, validate_slug
from django.db import transaction
from django.utils.text import slugify

from tenants.context import tenant_context
from tenants.models import Tenant
from tenants.provisioning import create_first_branch, create_tenant_admin, provision_tenant_defaults

User = get_user_model()


def clean(data):
    """(values, errors) from submitted onboarding fields."""
    errors = {}
    name = (data.get("name") or "").strip()
    slug = (data.get("slug") or slugify(name)).strip().lower()
    email = (data.get("admin_email") or "").strip().lower()
    values = {
        "name": name,
        "slug": slug,
        "email": email,
        "branch_name": (data.get("branch_name") or "الفرع الرئيسي").strip(),
        "branch_code": (data.get("branch_code") or "MAIN").strip().upper()[:20],
        "status": data.get("status") or Tenant.Status.TRIAL,
    }
    if not name:
        errors["name"] = ["اسم العيادة مطلوب."]
    if not slug:
        # slugify() returns "" for Arabic, and a blank slug is unusable.
        errors["slug"] = ["أدخل معرّفاً لاتينياً للعيادة (مثال: dr-ahmed)."]
    else:
        try:
            validate_slug(slug)
        except ValidationError:
            errors["slug"] = ["المعرّف يقبل حروفاً لاتينية وأرقاماً و - فقط."]
        if Tenant.objects.filter(slug=slug).exists():
            errors["slug"] = ["يوجد عيادة بهذا المعرّف بالفعل."]
    try:
        validate_email(email)
    except ValidationError:
        errors["admin_email"] = ["بريد إلكتروني غير صالح."]
    else:
        if User.objects.filter(email__iexact=email).exists():
            errors["admin_email"] = ["هذا البريد مستخدم بالفعل."]
    if values["status"] not in dict(Tenant.Status.choices):
        errors["status"] = ["حالة غير صالحة."]
    return values, errors


@transaction.atomic
def onboard(values, plan=None):
    """Create the group, its defaults, its first clinic and its owner.
    Returns (tenant, owner, password). `plan` replaces the default trial plan."""
    tenant = Tenant.objects.create(name=values["name"], slug=values["slug"], status=values["status"])
    provision_tenant_defaults(tenant)
    branch = create_first_branch(tenant, values["branch_name"], values["branch_code"])
    owner, password = create_tenant_admin(tenant, email=values["email"], username="admin", branch=branch)
    if plan is not None:
        from subscriptions.entitlements import current_subscription

        with tenant_context(tenant):
            subscription = current_subscription(tenant)
            if subscription is not None and subscription.plan_id != plan.pk:
                subscription.plan = plan
                subscription.save(update_fields=["plan", "updated_at"])
    return tenant, owner, password
