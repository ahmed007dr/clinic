"""Platform administration — doc/readme.md §10.

§10 asks for: create, approve, suspend and activate tenants; manage
subscriptions and plans; monitor payments, revenue and active clinics.

Everything here runs on the **normal** application connection, subject to the
same row-level security as every other request. Cross-tenant reach is achieved
by entering one tenant's context at a time and reading — never by holding a
privileged connection open. See permissions.py for why.

The one asymmetry worth stating plainly: clinical data is **read-only** here,
and always will be. The only tenant-owned write is changing which plan a clinic
is on, because that is the commercial relationship rather than a patient
record. Suspending or activating a tenant writes to `Tenant`, which is a
platform model and carries no isolation policy at all.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from appointments.models import Appointment
from billing.models import Payment
from branches.models import Branch
from employees.models import Employee
from medical.models import Visit
from patients.models import Patient
from subscriptions.entitlements import LIMITS, current_subscription, resolve_features
from subscriptions.usage import limits_table, usage_for
from subscriptions.models import Plan, Subscription
from tenants.context import tenant_context
from tenants.models import Tenant

from .audit import record
from .permissions import platform_staff_required


@login_required
@platform_staff_required
def tenant_list(request):
    """Every clinic on the platform, with the one number that matters per row.

    `Tenant`, `Plan` and `AuditLog` carry no isolation policy, so this listing
    needs no per-tenant binding. Anything counted *inside* a clinic does, which
    is why the counts below are gathered one tenant at a time rather than with
    a single annotated query — a join across tenant tables would return nothing
    on an unbound connection, and would look like a platform with no data.
    """
    rows = []
    for tenant in Tenant.objects.all():
        with tenant_context(tenant):
            subscription = current_subscription(tenant)
            rows.append({
                "tenant": tenant,
                "subscription": subscription,
                "plan": subscription.plan if subscription else None,
                "branches": Branch.objects.count(),
                "patients": Patient.objects.count(),
                "employees": Employee.objects.count(),
            })

    return render(request, "platform_admin/tenant_list.html", {
        "rows": rows,
        "statuses": Tenant.Status.choices,
    })


@login_required
@platform_staff_required
def tenant_detail(request, uuid):
    """One clinic, inspected read-only.

    Every figure below is read inside `tenant_context`, on the ordinary
    connection, so row-level security is doing exactly what it does for that
    clinic's own staff. Opening this page is itself recorded: the sensitive act
    is a platform operator looking at a clinic's record at all, and the
    change-tracking signals elsewhere only fire on writes.
    """
    tenant = get_object_or_404(Tenant, uuid=uuid)

    with tenant_context(tenant):
        subscription = current_subscription(tenant)
        # One definition of every count, shared with the clinic's own page and
        # every limit check (subscriptions/usage.py, WIRE-002).
        usage = usage_for(tenant)
        snapshot = {
            "appointments": Appointment.objects.count(),
            "visits": Visit.objects.count(),
            "revenue": Payment.objects.aggregate(total=Sum("amount"))["total"] or 0,
        }
        history = list(
            Subscription.objects.select_related("plan").all()[:20]
        )
        features = resolve_features(tenant)

    record(
        request, tenant, "inspect",
        f"viewed the platform overview for {tenant.slug}",
        model_name="Tenant", object_id=tenant.pk,
    )

    limits = limits_table(tenant, subscription, usage)

    return render(request, "platform_admin/tenant_detail.html", {
        "tenant": tenant,
        "subscription": subscription,
        "limits": limits,
        "snapshot": snapshot,
        "history": history,
        "features": sorted(features.items()),
        "plans": Plan.objects.filter(is_active=True),
        "statuses": Tenant.Status.choices,
    })


@login_required
@platform_staff_required
@require_POST
def tenant_set_status(request, uuid):
    """§10: approve, suspend, activate.

    Writes to `Tenant`, which is a platform model with no isolation policy — so
    this is not cross-tenant access to clinical data, it is the platform
    changing its own record of a customer. POST-only, and audited with both the
    old and the new value, because "who suspended this clinic and when" is the
    first question anyone asks afterwards.
    """
    tenant = get_object_or_404(Tenant, uuid=uuid)
    status = request.POST.get("status")

    if status not in dict(Tenant.Status.choices):
        messages.error(request, "حالة غير صالحة")
        return redirect("platform_admin:tenant_detail", uuid=tenant.uuid)

    previous = tenant.status
    if previous == status:
        messages.info(request, "الحالة لم تتغير")
        return redirect("platform_admin:tenant_detail", uuid=tenant.uuid)

    tenant.status = status
    tenant.save(update_fields=["status"])
    record(
        request, tenant, "tenant status",
        f"{tenant.slug}: {previous} -> {status}",
        model_name="Tenant", object_id=tenant.pk,
    )
    messages.success(request, f"تم تغيير حالة المستأجر إلى {tenant.get_status_display()}")
    return redirect("platform_admin:tenant_detail", uuid=tenant.uuid)


@login_required
@platform_staff_required
@require_POST
def tenant_change_plan(request, uuid):
    """§10: manage subscriptions.

    The **only** tenant-owned write available to platform staff, and bounded on
    purpose: it moves an existing subscription between plans and touches nothing
    else. It is the billing relationship, not a patient record.

    Done inside `tenant_context` like any other write to a tenant-owned row —
    the row-level security policy applies here exactly as it does to the
    clinic's own staff, which is the point of not having a privileged
    connection.
    """
    tenant = get_object_or_404(Tenant, uuid=uuid)
    plan = get_object_or_404(Plan, pk=request.POST.get("plan"), is_active=True)

    with tenant_context(tenant):
        subscription = current_subscription(tenant)
        if subscription is None:
            messages.error(request, "لا يوجد اشتراك نشط لهذا المستأجر")
            return redirect("platform_admin:tenant_detail", uuid=tenant.uuid)
        previous = subscription.plan
        if previous.pk == plan.pk:
            messages.info(request, "الباقة لم تتغير")
            return redirect("platform_admin:tenant_detail", uuid=tenant.uuid)
        subscription.plan = plan
        subscription.save(update_fields=["plan", "updated_at"])

    record(
        request, tenant, "plan change",
        f"{tenant.slug}: {previous.code} -> {plan.code}",
        model_name="Subscription", object_id=subscription.pk,
    )
    messages.success(request, f"تم تغيير الباقة إلى {plan.name}")
    return redirect("platform_admin:tenant_detail", uuid=tenant.uuid)
