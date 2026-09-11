"""The developer portal's business side — keys, mailboxes, subscription
billing, plans (docs/06 PLAT-002).

Same gate as api/platform.py (`IsPlatformStaff`: any operator reads, only a
full administrator changes). Every change is written to the audit trail — to
the group's own trail when it concerns one group, otherwise as a platform
event (tenant null).

Keys and passwords arrive here and nowhere else (the group owner's rule,
2026-09-11): they are encrypted on the way in (platform_admin/vault.py) and
only ever leave masked.
"""

from datetime import datetime, time

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework.response import Response
from rest_framework.views import APIView

from branches.models import Branch
from platform_admin import billing, checks, mailboxes, vault
from platform_admin.audit import record
from platform_admin.models import (
    CommercialTerms,
    Discount,
    IntegrationCredential,
    LateNote,
    Mailbox,
    PlatformInvoice,
    PlatformPayment,
)
from platform_admin.permissions import is_platform_staff
from subscriptions.entitlements import FEATURES, LIMITS
from subscriptions.models import Plan
from tenants.context import tenant_context
from tenants.models import Tenant

from .platform import IsPlatformStaff

Kind = IntegrationCredential.Kind
Scope = IntegrationCredential.Scope


def _error(message, code=400):
    return Response({"detail": str(message)}, status=code)


def _tenant(uuid):
    return get_object_or_404(Tenant, uuid=uuid)


def _customer(value):
    """The group named by a submitted uuid, or None (a malformed one too)."""
    if not value:
        return None
    try:
        return Tenant.objects.filter(uuid=value).first()
    except ValidationError:
        return None


def _branch_of(customer, branch_id):
    """A clinic of this group, read inside the group's own context (RLS)."""
    if not branch_id:
        return None
    try:
        branch_id = int(branch_id)
    except (TypeError, ValueError):
        return None
    with tenant_context(customer):
        return Branch.objects.filter(pk=branch_id).first()


def _money(value):
    return str(billing.money(value)) if value is not None else None


def _decimal(value):
    """A submitted number as money, or None when blank; ValueError otherwise."""
    if value in (None, ""):
        return None
    try:
        return billing.money(str(value))
    except Exception:  # noqa: BLE001 — decimal.InvalidOperation and friends
        raise ValueError(value)


class IsPlatformOperator(IsPlatformStaff):
    """Any operator, for actions that change nothing (a connection check)."""

    def has_permission(self, request, view):
        return is_platform_staff(request.user)


class TenantBranchesView(APIView):
    """A group's clinics, id and name only — for choosing where a key or a
    mailbox belongs."""

    permission_classes = [IsPlatformStaff]

    def get(self, request, uuid):
        customer = _tenant(uuid)
        with tenant_context(customer):
            rows = list(Branch.all_objects.filter(tenant=customer).order_by("name").values("id", "name", "is_active"))
        return Response(rows)


# ================================================================ integrations


def callback_urls(request):
    """The addresses to paste into each gateway's dashboard."""
    return {
        kind: request.build_absolute_uri(f"/api/pay/{kind}/callback/")
        for kind in (Kind.PAYMOB, Kind.FAWRY, Kind.VODAFONE_CASH)
    }


def save_credential(request, credential, data, created=False):
    try:
        previous_test = vault.unseal(credential.test_config)
        previous_production = vault.unseal(credential.production_config)
    except vault.VaultError:
        previous_test, previous_production = {}, {}
    try:
        if "test" in data:
            credential.test_config = vault.seal(vault.clean(credential.kind, data["test"], previous_test))
        if "production" in data:
            credential.production_config = vault.seal(
                vault.clean(credential.kind, data["production"], previous_production)
            )
    except vault.VaultError as error:
        return _error(error)
    if "mode" in data:
        if data["mode"] not in IntegrationCredential.Mode.values:
            return _error("البيئة: تجريبي أو إنتاج.")
        credential.mode = data["mode"]
    if "enabled" in data:
        credential.enabled = bool(data["enabled"])
    if "notes" in data:
        credential.notes = str(data["notes"] or "")[:300]
    live = vault.config_of(credential)
    if credential.enabled and vault.missing(credential.kind, live):
        return _error(
            f"بيانات بيئة «{credential.get_mode_display()}» ناقصة: "
            + "، ".join(vault.missing(credential.kind, live))
            + ". أكملها أو أوقف التكامل."
        )
    credential.updated_by = request.user
    try:
        credential.save()
    except IntegrityError:
        return _error("هذا التكامل مضبوط بالفعل لهذا المستوى.")
    # What changed, never the values.
    record(
        request, credential.customer, "integration " + ("added" if created else "changed"),
        f"{credential.kind} · {credential.scope}"
        + (f" · branch {credential.branch_id}" if credential.branch_id else "")
        + f" · mode {credential.mode} · {'on' if credential.enabled else 'off'}",
        model_name="IntegrationCredential", object_id=credential.pk,
    )
    return Response(vault.payload(credential), status=201 if created else 200)


class IntegrationListView(APIView):
    """GET: what may be set, and what is — optionally for one scope
    (`?scope=group&customer=<uuid>`, `?scope=clinic&customer=<uuid>&branch=<id>`).
    POST: add or replace one integration's settings for one scope."""

    permission_classes = [IsPlatformStaff]

    def get(self, request):
        credentials = IntegrationCredential.objects.select_related("customer", "updated_by")
        params = request.query_params
        if params.get("scope"):
            credentials = credentials.filter(scope=params["scope"])
        if params.get("customer"):
            credentials = credentials.filter(customer=_customer(params["customer"]))
        if params.get("branch"):
            credentials = credentials.filter(branch_id=params["branch"])
        items = []
        for credential in credentials:
            try:
                items.append(vault.payload(credential))
            except vault.VaultError as error:
                items.append({
                    "id": credential.pk, "kind": credential.kind, "scope": credential.scope,
                    "customer": str(credential.customer.uuid) if credential.customer_id else None,
                    "branch": credential.branch_id, "error": str(error),
                })
        return Response({
            "kinds": [
                {"kind": kind, "label": Kind(kind).label, "scopes": list(spec["scopes"]), "fields": spec["fields"]}
                for kind, spec in vault.FIELDS.items()
            ],
            "scopes": [{"value": value, "label": label} for value, label in Scope.choices],
            "items": items,
            "callback_urls": callback_urls(request),
        })

    @transaction.atomic
    def post(self, request):
        data = request.data
        kind, scope = data.get("kind"), data.get("scope")
        if kind not in vault.FIELDS:
            return _error("نوع تكامل غير معروف.")
        if scope not in vault.FIELDS[kind]["scopes"]:
            return _error("لا يُضبط هذا التكامل على هذا المستوى.")
        customer = branch = None
        if scope in (Scope.GROUP, Scope.CLINIC):
            customer = _customer(data.get("customer"))
            if customer is None:
                return _error("اختر المجموعة.")
        if scope == Scope.CLINIC:
            branch = _branch_of(customer, data.get("branch"))
            if branch is None:
                return _error("اختر العيادة.")
        credential = IntegrationCredential.objects.filter(
            kind=kind, scope=scope, customer=customer, branch=branch
        ).first()
        created = credential is None
        if created:
            credential = IntegrationCredential(kind=kind, scope=scope, customer=customer, branch=branch)
        return save_credential(request, credential, data, created=created)


class IntegrationDetailView(APIView):
    permission_classes = [IsPlatformStaff]

    def get(self, request, pk):
        return Response(vault.payload(get_object_or_404(IntegrationCredential, pk=pk)))

    @transaction.atomic
    def patch(self, request, pk):
        credential = get_object_or_404(IntegrationCredential.objects.select_for_update(), pk=pk)
        return save_credential(request, credential, request.data)

    def delete(self, request, pk):
        credential = get_object_or_404(IntegrationCredential, pk=pk)
        record(
            request, credential.customer, "integration removed", f"{credential.kind} · {credential.scope}",
            model_name="IntegrationCredential", object_id=credential.pk,
        )
        credential.delete()
        return Response(status=204)


class IntegrationTestView(APIView):
    """Try one environment's settings against the real service. Changes
    nothing, so support staff may run it too."""

    permission_classes = [IsPlatformOperator]

    def post(self, request, pk):
        credential = get_object_or_404(IntegrationCredential, pk=pk)
        mode = request.data.get("mode") or credential.mode
        if mode not in IntegrationCredential.Mode.values:
            return _error("البيئة: تجريبي أو إنتاج.")
        try:
            message = checks.run(credential, mode)
        except (checks.CheckFailed, vault.VaultError) as error:
            return Response({"ok": False, "detail": str(error)})
        return Response({"ok": True, "detail": message})


# ================================================================ mailboxes


def mailbox_payload(mailbox):
    return {
        "id": mailbox.pk,
        "address": mailbox.address,
        "customer": str(mailbox.customer.uuid),
        "customer_name": mailbox.customer.name,
        "branch": mailbox.branch_id,
        "quota_mb": mailbox.quota_mb,
        "used_for_sending": mailbox.used_for_sending,
        "created_at": mailbox.created_at,
        "created_by": getattr(mailbox.created_by, "email", None),
    }


class MailboxListView(APIView):
    permission_classes = [IsPlatformStaff]

    def get(self, request):
        items = Mailbox.objects.select_related("customer", "created_by")
        if request.query_params.get("customer"):
            items = items.filter(customer=_customer(request.query_params["customer"]))
        try:
            cpanel = vault.resolve(Kind.CPANEL)
        except vault.VaultError:
            cpanel = None
        return Response({
            "domain": cpanel[0]["domain"] if cpanel else None,
            "items": [mailbox_payload(m) for m in items],
        })

    def post(self, request):
        data = request.data
        customer = _customer(data.get("customer"))
        if customer is None:
            return _error("اختر المجموعة.")
        branch = _branch_of(customer, data.get("branch"))
        if data.get("branch") and branch is None:
            return _error("العيادة غير موجودة في هذه المجموعة.")
        try:
            quota = int(data.get("quota_mb") or 1024)
        except (TypeError, ValueError):
            return _error("المساحة بالميجابايت رقم.")
        try:
            mailbox, password = mailboxes.create(
                customer, data.get("local_part"), branch=branch, quota_mb=quota,
                use_for_sending=bool(data.get("use_for_sending", True)), actor=request.user,
            )
        except (mailboxes.MailboxError, vault.VaultError) as error:
            return _error(error)
        record(request, customer, "mailbox created", mailbox.address, model_name="Mailbox", object_id=mailbox.pk)
        # The password is shown this once; if the mailbox sends mail it lives
        # on only in the vault.
        return Response({**mailbox_payload(mailbox), "password": password}, status=201)


# ================================================================ billing


def terms_payload(terms):
    return {
        "cycle": terms.cycle,
        "cycle_label": terms.get_cycle_display(),
        "custom_price": _money(terms.custom_price),
        "currency": terms.currency,
        "next_invoice_on": terms.next_invoice_on,
        "notes": terms.notes,
    }


def discount_payload(discount, today=None):
    today = today or timezone.now().date()
    return {
        "id": discount.pk,
        "percent": str(discount.percent) if discount.percent is not None else None,
        "amount": _money(discount.amount),
        "starts_on": discount.starts_on,
        "ends_on": discount.ends_on,
        "reason": discount.reason,
        "active": discount.starts_on <= today <= discount.ends_on,
        "expired": discount.ends_on < today,
    }


def invoice_payload(invoice):
    paid = sum(
        (p.amount for p in invoice.payments.all() if p.status == PlatformPayment.Status.CONFIRMED),
        billing.ZERO,
    )
    void = invoice.status == PlatformInvoice.Status.VOID
    return {
        "id": invoice.pk,
        "number": invoice.number,
        "period_start": invoice.period_start,
        "period_end": invoice.period_end,
        "description": invoice.description,
        "base_amount": _money(invoice.base_amount),
        "discount_amount": _money(invoice.discount_amount),
        "total": _money(invoice.total),
        "paid": _money(paid),
        "remaining": "0.00" if void else _money(max(invoice.total - paid, billing.ZERO)),
        "currency": invoice.currency,
        "due_on": invoice.due_on,
        "overdue": invoice.status in ("open", "partial") and invoice.due_on < timezone.now().date(),
        "status": invoice.status,
        "status_label": invoice.get_status_display(),
        "notes": invoice.notes,
        "created_at": invoice.created_at,
    }


def payment_payload(payment):
    return {
        "id": payment.pk,
        "invoice": payment.invoice.number if payment.invoice_id else None,
        "amount": _money(payment.amount),
        "method": payment.method,
        "method_label": payment.get_method_display(),
        "status": payment.status,
        "status_label": payment.get_status_display(),
        "reference": payment.reference,
        "mode": payment.mode,
        "paid_at": payment.paid_at,
        "recorded_by": getattr(payment.recorded_by, "email", None),
    }


def billing_of(customer):
    terms = billing.terms_for(customer)
    try:
        price, description = billing.period_price(customer, terms)
        price_error = None
    except billing.BillingError as error:
        price, description, price_error = None, "", str(error)
    invoices = PlatformInvoice.objects.filter(customer=customer).prefetch_related("payments")
    payments = PlatformPayment.objects.filter(customer=customer).select_related("invoice", "recorded_by")
    return {
        "customer": {
            "uuid": str(customer.uuid), "name": customer.name, "status": customer.status,
            "status_label": customer.get_status_display(),
        },
        "terms": terms_payload(terms),
        "period_price": _money(price),
        "period_description": description,
        "period_price_error": price_error,
        "discounts": [discount_payload(d) for d in Discount.objects.filter(customer=customer)],
        "invoices": [invoice_payload(i) for i in invoices],
        "payments": [payment_payload(p) for p in payments[:200]],
        "account": billing.account(customer),
        "late_history": [
            {"note": n.note, "since": n.created_at, "resolved_at": n.resolved_at}
            for n in LateNote.objects.filter(customer=customer)[:20]
        ],
    }


class BillingListView(APIView):
    """Every group's balance — the "customers and balances" list."""

    permission_classes = [IsPlatformStaff]

    def get(self, request):
        terms = {t.customer_id: t for t in CommercialTerms.objects.all()}
        rows = []
        totals = {"invoiced": billing.ZERO, "paid": billing.ZERO, "balance": billing.ZERO}
        for customer in Tenant.objects.order_by("name"):
            account = billing.account(customer)
            term = terms.get(customer.pk)
            rows.append({
                "uuid": str(customer.uuid), "name": customer.name, "status": customer.status,
                "status_label": customer.get_status_display(),
                "cycle": term.cycle if term else CommercialTerms.Cycle.MONTHLY,
                "custom_price": _money(term.custom_price) if term else None,
                "next_invoice_on": term.next_invoice_on if term else None,
                **account,
            })
            for key in totals:
                totals[key] += billing.money(account[key])
        return Response({"items": rows, "totals": {k: _money(v) for k, v in totals.items()}})


class TenantBillingView(APIView):
    """One group's terms, discounts, invoices, payments and balance.
    PATCH changes the terms (cycle, negotiated price, next invoice date)."""

    permission_classes = [IsPlatformStaff]

    def get(self, request, uuid):
        return Response(billing_of(_tenant(uuid)))

    def patch(self, request, uuid):
        customer = _tenant(uuid)
        terms = billing.terms_for(customer)
        data = request.data
        if "cycle" in data:
            if data["cycle"] not in CommercialTerms.Cycle.values:
                return _error("الدورة: شهري أو سنوي.")
            terms.cycle = data["cycle"]
        if "custom_price" in data:
            try:
                terms.custom_price = _decimal(data["custom_price"])
            except ValueError:
                return _error("السعر رقم.")
            if terms.custom_price is not None and terms.custom_price < 0:
                return _error("السعر لا يكون سالباً.")
        if "next_invoice_on" in data:
            value = data["next_invoice_on"]
            terms.next_invoice_on = parse_date(str(value)) if value else None
            if value and terms.next_invoice_on is None:
                return _error("تاريخ الفاتورة القادمة غير صالح.")
        if data.get("currency"):
            terms.currency = str(data["currency"])[:3].upper()
        if "notes" in data:
            terms.notes = str(data["notes"] or "")
        terms.save()
        record(
            request, customer, "billing terms",
            f"cycle {terms.cycle}, price {terms.custom_price if terms.custom_price is not None else 'plan'}, "
            f"next invoice {terms.next_invoice_on or '-'}",
            model_name="CommercialTerms", object_id=terms.pk,
        )
        return Response(billing_of(customer))


class DiscountView(APIView):
    """POST: a discount for a limited period; DELETE `?id=`: remove one."""

    permission_classes = [IsPlatformStaff]

    def post(self, request, uuid):
        customer = _tenant(uuid)
        data = request.data
        starts = parse_date(str(data.get("starts_on") or ""))
        ends = parse_date(str(data.get("ends_on") or ""))
        if not starts or not ends:
            return _error("حدد تاريخ بداية ونهاية الخصم.")
        if ends < starts:
            return _error("تاريخ النهاية قبل البداية.")
        try:
            percent, amount = _decimal(data.get("percent")), _decimal(data.get("amount"))
        except ValueError:
            return _error("قيمة الخصم رقم.")
        if percent is None and amount is None:
            return _error("حدد نسبة أو مبلغاً أو كليهما.")
        if percent is not None and not (0 < percent <= 100):
            return _error("النسبة بين 0 و 100.")
        if amount is not None and amount <= 0:
            return _error("المبلغ أكبر من صفر.")
        discount = Discount.objects.create(
            customer=customer, percent=percent, amount=amount, starts_on=starts, ends_on=ends,
            reason=str(data.get("reason") or "")[:200], created_by=request.user,
        )
        record(
            request, customer, "discount added", f"{percent or 0}% + {amount or 0} from {starts} to {ends}",
            model_name="Discount", object_id=discount.pk,
        )
        return Response(billing_of(customer), status=201)

    def delete(self, request, uuid):
        customer = _tenant(uuid)
        discount = get_object_or_404(Discount, pk=request.query_params.get("id"), customer=customer)
        record(request, customer, "discount removed", f"#{discount.pk}", model_name="Discount", object_id=discount.pk)
        discount.delete()
        return Response(billing_of(customer))


class InvoiceIssueView(APIView):
    """Issue the next period's invoice now (the daily cron does the same for
    groups whose date has come: `manage.py issue_platform_invoices`)."""

    permission_classes = [IsPlatformStaff]

    def post(self, request, uuid):
        customer = _tenant(uuid)
        raw = request.data.get("period_start")
        start = parse_date(str(raw)) if raw else None
        if raw and start is None:
            return _error("تاريخ بداية الفترة غير صالح.")
        try:
            invoice = billing.issue_invoice(customer, actor=request.user, period_start=start)
        except billing.BillingError as error:
            return _error(error)
        record(
            request, customer, "invoice issued", f"{invoice.number}: {invoice.total}",
            model_name="PlatformInvoice", object_id=invoice.pk,
        )
        return Response(billing_of(customer), status=201)


class InvoiceVoidView(APIView):
    permission_classes = [IsPlatformStaff]

    def post(self, request, pk):
        invoice = get_object_or_404(PlatformInvoice, pk=pk)
        if invoice.status == PlatformInvoice.Status.VOID:
            return _error("الفاتورة ملغاة بالفعل.")
        if invoice.payments.filter(status=PlatformPayment.Status.CONFIRMED).exists():
            return _error("على الفاتورة مدفوعات مؤكدة؛ لا تُلغى.")
        reason = str(request.data.get("reason") or "").strip()
        if not reason:
            return _error("اكتب سبب الإلغاء.")
        billing.void_invoice(invoice, reason)
        record(
            request, invoice.customer, "invoice voided", f"{invoice.number}: {reason}",
            model_name="PlatformInvoice", object_id=invoice.pk,
        )
        return Response(billing_of(invoice.customer))


class ManualPaymentView(APIView):
    """Cash or bank transfer, recorded by the operator."""

    permission_classes = [IsPlatformStaff]

    def post(self, request, uuid):
        customer = _tenant(uuid)
        data = request.data
        method = data.get("method")
        if method not in (PlatformPayment.Method.CASH, PlatformPayment.Method.TRANSFER):
            return _error("سجّل هنا الدفع النقدي أو التحويل البنكي فقط.")
        invoice = None
        if data.get("invoice"):
            invoice = PlatformInvoice.objects.filter(pk=data["invoice"], customer=customer).first()
            if invoice is None:
                return _error("الفاتورة غير موجودة لهذه المجموعة.")
            if invoice.status == PlatformInvoice.Status.VOID:
                return _error("الفاتورة ملغاة.")
        paid_at = None
        if data.get("paid_at"):
            paid_at = parse_datetime(str(data["paid_at"]))
            if paid_at is None:
                day = parse_date(str(data["paid_at"]))
                if day is None:
                    return _error("تاريخ الدفع غير صالح.")
                paid_at = datetime.combine(day, time(12))
                if settings.USE_TZ:
                    paid_at = timezone.make_aware(paid_at)
        reference = str(data.get("reference") or "").strip()
        if method == PlatformPayment.Method.TRANSFER and not reference:
            return _error("اكتب رقم التحويل أو مرجعه.")
        try:
            amount = _decimal(data.get("amount"))
        except ValueError:
            return _error("المبلغ رقم.")
        try:
            payment = billing.record_payment(
                customer, amount or 0, method, actor=request.user, invoice=invoice,
                reference=reference, paid_at=paid_at,
            )
        except billing.BillingError as error:
            return _error(error)
        record(
            request, customer, "payment recorded",
            f"{payment.amount} {payment.method}" + (f" for {invoice.number}" if invoice else ""),
            model_name="PlatformPayment", object_id=payment.pk,
        )
        return Response(billing_of(customer), status=201)


class LateView(APIView):
    """POST {note}: record the group as late. DELETE: clear it."""

    permission_classes = [IsPlatformStaff]

    def post(self, request, uuid):
        customer = _tenant(uuid)
        note = str(request.data.get("note") or "").strip()
        billing.mark_late(customer, note, actor=request.user)
        record(request, customer, "marked late", note or "-", model_name="LateNote")
        return Response(billing_of(customer))

    def delete(self, request, uuid):
        customer = _tenant(uuid)
        billing.clear_late(customer)
        record(request, customer, "late cleared", "-", model_name="LateNote")
        return Response(billing_of(customer))


# ================================================================ plans


def plan_payload(plan):
    return {
        "id": plan.pk,
        "code": plan.code,
        "name": plan.name,
        "description": plan.description,
        "billing_period": plan.billing_period,
        "billing_period_label": plan.get_billing_period_display(),
        "price": _money(plan.price),
        "currency": plan.currency,
        "limits": plan.limits,
        "features": plan.features,
        "is_active": plan.is_active,
        "is_public": plan.is_public,
    }


def apply_plan(plan, data):
    """Copy the submitted fields onto `plan`; returns a problem or None."""
    for name in ("name", "description", "currency"):
        if name in data:
            setattr(plan, name, str(data[name] or "").strip())
    if "code" in data and not plan.pk:
        plan.code = str(data["code"] or "").strip()
    if "billing_period" in data:
        if data["billing_period"] not in Plan.BillingPeriod.values:
            return "دورة الفوترة غير صالحة."
        plan.billing_period = data["billing_period"]
    if "price" in data:
        try:
            plan.price = _decimal(data["price"]) or billing.ZERO
        except ValueError:
            return "السعر رقم."
        if plan.price < 0:
            return "السعر لا يكون سالباً."
    limits = data.get("limits") or {}
    for name in LIMITS:
        if name in limits:
            value = limits[name]
            if value in (None, ""):
                setattr(plan, name, None)
                continue
            try:
                setattr(plan, name, max(int(value), 0))
            except (TypeError, ValueError):
                return "الحدود أرقام صحيحة (فارغ = غير محدود)."
    if "features" in data:
        features = data["features"] or {}
        unknown = set(features) - set(FEATURES)
        if unknown:
            return "ميزة غير معروفة: " + "، ".join(sorted(unknown))
        plan.features = {key: bool(value) for key, value in features.items()}
    for flag in ("is_active", "is_public"):
        if flag in data:
            setattr(plan, flag, bool(data[flag]))
    if not plan.name or not plan.code:
        return "الاسم والرمز مطلوبان."
    try:
        plan.full_clean()
    except ValidationError as error:
        return "؛ ".join(f"{k}: {' '.join(v)}" for k, v in error.message_dict.items())
    return None


class PlanManageView(APIView):
    """Every plan, offered or not; POST adds one."""

    permission_classes = [IsPlatformStaff]

    def get(self, request):
        from api.views.subscription import FEATURE_LABELS

        return Response({
            "items": [plan_payload(p) for p in Plan.objects.order_by("price", "name")],
            "limits": [{"key": k, "label": v} for k, v in LIMITS.items()],
            "features": [{"key": k, "label": FEATURE_LABELS.get(k, v[0])} for k, v in FEATURES.items()],
            "billing_periods": [{"value": v, "label": label} for v, label in Plan.BillingPeriod.choices],
        })

    def post(self, request):
        plan = Plan()
        problem = apply_plan(plan, request.data)
        if problem:
            return _error(problem)
        plan.save()
        record(request, None, "plan added", f"{plan.code}: {plan.price}", model_name="Plan", object_id=plan.pk)
        return Response(plan_payload(plan), status=201)


class PlanDetailView(APIView):
    permission_classes = [IsPlatformStaff]

    def patch(self, request, pk):
        plan = get_object_or_404(Plan, pk=pk)
        before = plan_payload(plan)
        problem = apply_plan(plan, request.data)
        if problem:
            return _error(problem)
        plan.save()
        after = plan_payload(plan)
        changed = [key for key in after if after[key] != before[key]]
        record(
            request, None, "plan changed", f"{plan.code}: {', '.join(changed) or '-'}",
            model_name="Plan", object_id=plan.pk,
        )
        return Response(after)


