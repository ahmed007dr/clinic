# 11 — Frontend/Backend Wiring Plan

Status values: `TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`, `NEEDS_REVIEW`.

This batch closes the gaps found by the two-way connectivity audit of 2026-09-09:
every route in the backend checked for a way to reach it from the UI, and every
link, form and template checked for a route behind it.

The audit's headline is that the application is **almost** fully wired — 87
routes across 12 apps, every view routed, every app template rendered by a view,
no AJAX and therefore no hidden endpoints. What it found is not a missing layer
but ten specific breaks, and they are not equally serious. One is a crash. Three
are commercial controls that were designed, documented, stored and displayed —
and then never enforced. The rest are entry points that exist and cannot be
reached.

The ordering below is by consequence, not by effort.

---

## Task list

| ID | Task | Priority | Status |
|---|---|---|---|
| WIRE-001 | A page that 500s, and the test that would have caught it | P0 | TODO |
| WIRE-002 | One place that counts usage against a plan | P1 | TODO |
| WIRE-003 | Enforce `max_doctors` and `max_staff` | P1 | TODO |
| WIRE-004 | Storage accounting, and `max_storage_mb` | P1 | TODO |
| WIRE-005 | Features: enforce the one that exists, fail the suite on the rest | P1 | TODO |
| WIRE-006 | PLAT-006 — something actually invokes the report generators | P2 | TODO |
| WIRE-007 | FE-026 — a clinic can see its own plan, limits and usage | P2 | TODO |
| WIRE-008 | FE-027 entry — reachable audit log, subscription and operator portal | P2 | TODO |
| WIRE-009 | Marking a notification read is a GET that changes state | P2 | TODO |
| WIRE-010 | Cleanup: namespace mismatch, dead theme files | P3 | TODO |

---

## P0 — the break that is visible to a user today

### WIRE-001 — A page that 500s, and the test that would have caught it

**The defect.** [`employees/templates/employees/specialization_update.html:38`](../employees/templates/employees/specialization_update.html#L38) reverses `{% url 'specialization_list' %}` without the app namespace. Confirmed against the real resolver:

```
employees:specialization_list -> /employees/specialization/
specialization_list           -> NoReverseMatch
```

The template raises while rendering, so **the specialization edit screen returns 500 on GET** — the failure is not on submit, it is on open. The two sibling templates (`specialization_create.html`, `specialization_delete.html`) get it right, so this is a single-line slip, not a misunderstanding.

**Why it survived.** No test opens this page. Searching for `specialization_update` finds it in `urls.py` and `views.py` and nowhere else.

**The fix.** Add the namespace. That is one line.

**The fix that matters.** A one-line correction leaves the *class* of defect alive — any of the ~120 `{% url %}` tags across 74 templates can be mistyped the same way, and the only detector today is a user opening the page. [`dashboard/tests.py`](../dashboard/tests.py) already establishes the right pattern: `test_every_referenced_asset_resolves` scans every template for `{% static %}` references and asserts each one exists. Add its sibling:

- Scan every template in the project (excluding `venv/`, `staticfiles/`) for `{% url '<name>' %}`.
- For each name, assert it is **registered** with the URL resolver — registration, not `reverse()`, because most of these take arguments (`<uuid:uuid>`) a scanner cannot supply. Walk `get_resolver().reverse_dict` plus each namespace's own resolver.
- Names from included apps (`admin:*`, `password_reset_confirm`, `django-admindocs-*`) resolve through the same walk, so no allowlist should be needed; if one turns out to be, it goes in the test with a stated reason.

**Done when.** The namespace is fixed, the scanner test passes, and reverting the namespace fix makes it fail. Mutation-test it the way DEPLOY-003 was.

**Risk.** None. No schema change, no behaviour change beyond a page that stops crashing.

---

## P1 — controls that were built and never connected

These are the serious ones. [`subscriptions/entitlements.py`](../subscriptions/entitlements.py) is careful, well-argued code that fails closed by design. Five limits are defined; **two are enforced**. Six features are defined, stored, validated, resolved with plan-then-override precedence, and displayed in the operator portal; **none is enforced anywhere**. A tenant on the smallest plan can create unlimited doctors, unlimited staff and unlimited storage today, and nothing in the system objects.

The module is not at fault — `check_limit` and `require_feature` are correct and ready. Nothing calls them.

### WIRE-002 — One place that counts usage against a plan

**Why this comes first.** The counting rules already exist in code once, inline: [`platform_admin/views.py:84-95`](../platform_admin/views.py#L84-L95) computes usage including the non-obvious rule that "doctors" means `Employee.objects.filter(employee_type__name="Doctor")`. WIRE-003, WIRE-004 and WIRE-007 all need the same numbers. If each writes its own count, the screen and the enforcement will eventually disagree — and the failure mode is a clinic being told it has room for one more doctor by a page whose count is computed differently from the check that then refuses it.

**The work.** New module `subscriptions/usage.py`:

- `usage_for(tenant)` → the `{limit_field: count}` dict currently inline in `tenant_detail`. It must be called *inside* `tenant_context` by its caller rather than entering the context itself — `platform_admin` deliberately controls when that happens, and [`permissions.py`](../platform_admin/permissions.py) explains at length why that control must not spread.
- `limits_table(tenant)` → the `used / allowed / unlimited / over` rows currently built at [`platform_admin/views.py:110-121`](../platform_admin/views.py#L110-L121).
- `tenant_detail` then calls both instead of computing them: ~30 lines lighter, and one definition of every count.

**Done when.** `platform_admin` renders identically and its existing tests pass unchanged, and the new module is the only place that knows how a doctor is counted.

### WIRE-003 — Enforce `max_doctors` and `max_staff`

**Where.** [`employees/views.py:13`](../employees/views.py#L13), `employee_create`. Follow the established shape from [`branches/views.py:21`](../branches/views.py#L21) and [`patients/views.py:38`](../patients/views.py#L38): check **after** `form.is_valid()` (the employee type is only known once the form has cleaned it) and **before** `form.save()`, catch `LimitReached`, message in Arabic, redirect to the list.

**Two limits, one form.** `max_staff` counts every employee. `max_doctors` applies only when the submitted `employee_type` is the Doctor type — so that check is conditional on `form.cleaned_data['employee_type']`. Both are checked, staff first.

**Also `employee_update`.** It can move an existing employee *into* the Doctor type, which is the same limit crossed by a different door. Decide explicitly rather than by omission. Recommendation: check it there too — a limit that only guards the create path is a limit with a documented bypass.

**The message.** Matching the two that exist, and — once WIRE-007 lands — linking to the subscription page instead of saying "قم بترقية الباقة" with nowhere to go.

**Done when.** At the limit the POST is refused, no row is created, and the message names the allowance; under the limit it saves; a `null` allowance (unlimited) never refuses; a tenant with no active subscription gets 0 and is refused, per the module's fail-closed contract.

### WIRE-004 — Storage accounting, and `max_storage_mb`

**The state today.** [`platform_admin/views.py:91`](../platform_admin/views.py#L91) reads:

```python
"max_storage_mb": None,  # storage accounting is not implemented yet
```

It is the only limit with no number behind it — yet the number is already stored. `MedicalAttachment.size_bytes` is a `PositiveBigIntegerField` populated on every upload, and `size_display` already formats it.

**The work.**

- `usage_for` (WIRE-002) computes `max_storage_mb` as `MedicalAttachment.objects.aggregate(Sum("size_bytes"))` converted to whole MB, so the operator's screen stops showing a blank.
- [`medical/views.py`](../medical/views.py), `attachment_upload`: after `form.is_valid()`, before `form.save()`, check current usage **plus the incoming file** against the allowance. The incoming size is available as `form.cleaned_data["file"].size` without touching disk — which matters, because the refusal must happen *before* the file is written, not after.
- The refusal is an Arabic message on the same form, sitting alongside the existing per-file `MEDICAL_ATTACHMENT_MAX_BYTES` rejection rather than replacing it: one caps a single file, the other caps the tenant's total.

**A note on the honesty of the number.** There is no delete view for attachments (deliberate — clinical retention, MED-011), so the sum only grows and cannot drift from reality. If a delete path is ever added this becomes a cached-count problem; leave a comment saying so rather than pre-building for it.

**Done when.** A tenant at its storage allowance is refused with the file unwritten, the operator's tenant page shows real megabytes, and unlimited plans are unaffected.

### WIRE-005 — Features: enforce the one that exists, fail the suite on the rest

**The honest position.** Of the six features in `FEATURES`, exactly one has an implementation to gate:

| Feature | Implementation | Action |
|---|---|---|
| `reports` | the generators in `reports/views.py` | Gate in WIRE-006 |
| `whatsapp` | none — PLAT-004 not started | Leave; declare |
| `online_payments` | none — FIN-004/005 not started | Leave; declare |
| `advanced_analytics` | none | Leave; declare |
| `ai` | none | Leave; declare |
| `packages` | none as such | Leave; declare |

**What must not be done.** `advanced_analytics` is tempting to wire to `billing:financial_report`, and `packages` to treatment plans. Both would be wrong. Those screens work for every tenant today; putting them behind a flag that defaults to `False` **removes working functionality from paying customers** on the next deploy. That is a regression dressed as a fix. If the business wants the financial report to become a paid tier, that is a pricing decision with a data migration to set the flag on existing plans — not a wiring task, and it does not belong in this batch.

**The mechanism that stops the drift recurring.** The real failure was not any single missing call; it was that a feature could be added to the registry, stored, validated, displayed — and enforced nowhere, forever, silently. Following the pattern `tenants/rls.py` established for RLS membership (derive, don't list), add a test asserting that every key in `FEATURES` is either referenced by a `require_feature`/`has_feature` call in the source, or named in an explicit `NOT_YET_IMPLEMENTED` set carrying a reason. A seventh feature added without wiring then fails the suite instead of shipping inert.

**Done when.** `reports` is enforced (WIRE-006), the other five are declared with reasons, and the registry test refuses a new unwired feature.

---

## P2 — backends with no way in

### WIRE-006 — PLAT-006: something actually invokes the report generators

**The state today.** [`reports/views.py`](../reports/views.py) holds three complete, tenant-aware generators — `generate_daily_report`, `generate_monthly_report`, `generate_annual_report` — each looping tenants inside `tenant_context`, rendering an email template and sending to active `ReportRecipient`s. A search across the repository finds **no caller**: no management command, no cron entry, no view, no scheduler. `ReportRecipient` has a Django-admin screen and nothing else. Already tracked as PLAT-006 in [08-backend-plan.md](08-backend-plan.md) §7 — "the generators exist but nothing invokes them".

The three templates under `reports/templates/` are email bodies rendered via `render_to_string`, not web pages, so they are correctly connected. It is the trigger that is missing.

**The work.**

- Management command `reports/management/commands/send_scheduled_reports.py` taking `--period daily|monthly|annual` (default `daily`) and `--dry-run` — report what would be sent and to whom, send nothing. The first live run of an emailer should be observable before it is trusted.
- Keep the tenant loop where it is. Moving it into the command is defensible but a larger diff, and the generators already do it correctly.
- **Two new gates per tenant:** skip a tenant whose subscription lacks the `reports` feature (WIRE-005), and skip a tenant whose status is not `ACTIVE` or `TRIAL` — a suspended or cancelled clinic should not be receiving revenue emails. `Tenant.Status` is `trial / active / suspended / cancelled`.
- Report on stdout what it did: tenants considered, tenants skipped and why, emails sent. A cron job that prints nothing is a cron job nobody notices has stopped.

**Deployment.** The target is cPanel (DEPLOY-004), so this is a cPanel cron entry — not systemd, not Celery. Add it to [10-deployment-runbook.md](10-deployment-runbook.md) with the absolute interpreter path, the three schedules, and the warning that the daily report must run *after* the clinic closes rather than at 00:00, or it reports on an empty day. PLAT-005 (a real job runner) stays out of scope: cron is the right amount of machinery for three emails a day.

**Testing.** With the `locmem` email backend — a tenant with the feature and active recipients gets mail; one without the feature does not; a suspended tenant does not; a tenant with no active recipients does not (BE-001 already handles this, so assert it stays handled); `--dry-run` sends nothing.

**Done when.** `send_scheduled_reports --period daily --dry-run` names the right tenants on the demo dataset, a live run sends, and the runbook carries the cron lines.

### WIRE-007 — FE-026: a clinic can see its own plan, limits and usage

**The gap.** `subscriptions/` has models, entitlements and an admin — no `urls.py`, no views, no templates. A clinic administrator cannot see which plan they are on, what it allows, how much of it they have used, or when it expires. All of that exists and is rendered, but only in `platform_admin`, for the operator. The tenant sees nothing until a limit refuses them — and the message then tells them to upgrade a plan they have no way to look at.

**The work.**

- `subscriptions/urls.py` and a `subscription_detail` view, Admin-only (`user_passes_test` on `role.name == 'Admin'`, matching every other admin screen).
- Mounted in [`project/urls.py`](../project/urls.py) at `subscription/`. The catch-all `path('<path:unused_path>/', …)` sits last and will not shadow it.
- Template `subscriptions/detail.html` extending `base.html`: plan name and price, status and dates (`started_on`, `ends_on`, `trial_ends_on`), the limits table from WIRE-002 with used/allowed and an over-limit highlight, and the resolved feature list from `resolve_features`.
- **Read-only.** No self-serve upgrade, no plan change, no payment. P4 in [06-implementation-progress.md](06-implementation-progress.md) records that billing integration is blocked on a gateway and credentials rather than on engineering, so this page ends with "contact us to upgrade" and not a button that cannot work.
- The `LimitReached` messages in `branches`, `patients` and — new — `employees` and `medical` link here.

**Security note worth stating explicitly.** This page renders the tenant's *own* subscription, derived from `request.user.tenant` and nothing else, never from a URL parameter. Cross-tenant reach is `platform_admin`'s job and stays there.

**Done when.** An Admin sees their plan and usage; Reception and Doctor are refused; and the figures match what the operator portal shows for the same tenant — which, since both call WIRE-002, is a test that the two callers agree.

### WIRE-008 — FE-027 entry: three screens that exist and cannot be reached

None of these needs new backend work. All three are routes with views, templates and tests, and no link anywhere in the UI.

| Route | Reachable today by | Add to |
|---|---|---|
| `audit:audit_list` (`/audit/`) | typing the URL | `base.html`, inside the existing `{% if request.user.role.name == 'Admin' %}` block — the view is already Admin-gated by SEC-007, so link and view agree |
| `subscriptions:subscription_detail` (WIRE-007) | — | the same Admin block, or the profile dropdown beside "إعدادات" |
| `platform_admin:tenant_list` (`/platform/`) | typing the URL | a new `{% if request.user.is_platform_staff %}` block |

**The platform-staff case needs care.** Platform staff carry `tenant_id = None` and no `ClinicRole` by design ([`platform_admin/permissions.py`](../platform_admin/permissions.py)). `base.html` reads `request.user.role.name` throughout; against `None` Django's template layer resolves that to the empty string rather than raising, so an operator currently sees the reduced navigation without an error. Verify that rather than assume it — render `base.html` as a platform user in a test — and give them their own link block so the operator portal is reachable from the page they land on.

**Done when.** Tests assert the audit link appears for Admin and not for Reception, and the platform link appears for platform staff and for nobody else. A link rendered for a user the view would refuse is worse than no link at all.

### WIRE-009 — Marking a notification read is a GET that changes state

**What the audit turned up.** [`notifications/templates/notifications/mark_read.html`](../notifications/templates/notifications/mark_read.html) is an orphan: a complete POST confirmation page, CSRF token and all, that **no view renders**. Following that thread explains why it exists. [`notifications/list.html:41`](../notifications/templates/notifications/list.html#L41) triggers the action with a plain `<a href>`, and [`notification_mark_read`](../notifications/views.py) writes and redirects on **GET**.

So this is not a stray file. It is a state-changing GET with no CSRF protection, and the confirmation page meant to prevent it was written and never wired up. Anything that can make the browser issue that URL — an `<img>` in an email, a prefetch, a link scanner — marks a clinician's notification read. The impact is small (one boolean, scoped to the user's own rows, already hardened with `get_object_or_404`) but the shape is a textbook CSRF, and it is one decorator away from correct.

**The fix.** `@require_POST` on the view, and the list's link becomes a small POST form with `{% csrf_token %}`. The orphan template then either becomes the GET half — a confirmation page for a client without JS — or is deleted. Recommendation: delete it and keep the POST button. A confirmation dialogue for "mark as read" is friction that protects nothing.

**Done when.** GET on the URL returns 405, the button still works, and a test asserts both.

---

## P3 — cleanup

### WIRE-010

- **`notifications` namespace mismatch.** [`notifications/urls.py`](../notifications/urls.py) declares `app_name = "notification"` (singular) and survives only because [`project/urls.py:27`](../project/urls.py#L27) passes `namespace="notifications"` in the tuple form, which wins. Every template already uses `notifications:`. Correct the declaration; nothing changes today, but a future plain `include('notifications.urls')` would break every notification link at once.
- **Dead theme files.** `static/partials/_horizontal-navbar.html`, `static/partials/_footer.html` and `static/docs/documentation.html` are untouched vendor-theme leftovers full of dummy links (`pages/ui-features/buttons.html`, `index.html`). There is not a single `{% include %}` in the project. They are harmless, but they are the first thing a newcomer greps into. Removing them touches the tracked asset set that P0 established, so confirm `dashboard/tests.py` still passes rather than assuming — those tests scan `templates/` for `{% static %}` references and should be indifferent to these files, but "should be" is exactly why the test exists.

---

## Order, and why

1. **WIRE-001** first and alone — a user-visible crash should not wait behind a refactor, and the scanner test it brings protects every task after it.
2. **WIRE-002** next, because 003, 004 and 007 all consume it. Doing it afterwards means writing the same count three times and then unifying it.
3. **WIRE-003, WIRE-004, WIRE-005** — the commercial controls, in that order: staff/doctors is the simplest, storage needs the aggregate, features needs the registry test. These are the batch's real content; everything else is a link.
4. **WIRE-006** — reports. Independent of the above apart from the `reports` gate, so it can move earlier if the cron matters more than the limits do.
5. **WIRE-007** then **WIRE-008** — the page must exist before it is linked, and the `LimitReached` messages from step 3 point at it once it does.
6. **WIRE-009, WIRE-010** — small, independent, safe to land at any point.

## Verification for the batch as a whole

- `manage.py check` clean, and `check --deploy` showing only the known HSTS warning (DEPLOY-001).
- Full suite green on both supported backends — PostgreSQL 17 and SQLite — since WIRE-004's `Sum` aggregate and the RLS policies are the parts most likely to differ between them.
- Re-run the connectivity audit that produced this document: no unresolved `{% url %}` name, no route unreachable from the UI except by deliberate decision, no orphan template.
- Exercise it against `seed_demo` data, not only against tests. The demo dataset exists precisely so entitlement checks can be tried honestly (DEPLOY-007), and every limit in this batch should be walked into on real seeded data before it is called done.

## Explicitly out of scope

- **Gating `advanced_analytics`, `packages`, `whatsapp`, `online_payments`, `ai`.** No implementation to gate, and flipping working screens behind a default-`False` flag is a regression. See WIRE-005.
- **Self-serve plan upgrades and payment.** Blocked on a gateway and credentials (P4), not on this batch.
- **A job runner (PLAT-005).** Cron is sufficient for WIRE-006 and correct for the cPanel target.
- **The Patient Portal, and any React.** The architectural direction is settled: the staff application stays on Django templates.
