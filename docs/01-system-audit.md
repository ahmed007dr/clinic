# 01 — System Audit

Scope: full read of every app's `models.py`, `views.py`, `urls.py`, `settings.py`, `project/urls.py`, `.gitignore`, git log, and representative `forms.py`. Every finding below is backed by a file:line reference read directly from this repository on 2026-09-07 — nothing here is inferred from `doc/readme.md`'s aspirational spec.

This was originally recorded as a **live production system holding real patient data**, inferred from the presence of `passenger_wsgi.py`, the git log message "passenger cpanel", and the `2odays.com` domain. **That inference did not survive verification and has been withdrawn** — see the Gate A findings in [06-implementation-progress.md](06-implementation-progress.md). In summary:

- `passenger_wsgi.py` was live for exactly one day (2025-09-28) and has been **entirely commented out** since 2025-09-29, so it defines no `application` callable and Passenger cannot boot from it.
- **`2odays.com` does not resolve.** Public DNS returns SERVFAIL for A, SOA and NS, so its delegation is broken or absent.
- No Passenger configuration has ever been tracked in this repository (no `.htaccess`), so production configuration lives entirely outside it.
- `club-ft.com` is a **different Django project** and must not be read as this application's production.

**The location of any real patient data is currently unknown, and no migration or deployment should happen until it is confirmed.** The security findings below stand on their own merits regardless — they are defects in the code as written. Findings are ordered by severity.

---

## CRITICAL

### C1 — Live secrets committed to git
[project/settings.py:23](../project/settings.py#L23) — `SECRET_KEY` is Django's own scaffold-generated "insecure" default, unchanged, committed to source control.
[project/settings.py:166-172](../project/settings.py#L166-L172) — `EMAIL_HOST_PASSWORD = 'z75.l5aCQgU6.H'` for the live mailbox `dr-ahmed@2odays.com` is committed in plaintext, along with host/port/user.
**Impact**: anyone with read access to the repo (or its history — these values were committed, so rotating them going forward doesn't erase the exposure) can forge signed sessions/cookies and send mail as the clinic's address.
**Fix direction**: rotate the `SECRET_KEY` and the email password immediately, move both to environment variables (the project already depends on `django-environ` but never uses it), and treat the git history as compromised — consider it public knowledge going forward.

### C2 — `DEBUG = True` with no environment guard
[project/settings.py:26](../project/settings.py#L26) — hardcoded `True`, no `env.bool(...)` despite `django-environ` being installed. If this reaches production as-is, Django serves full stack traces (source code, local variables, settings) on any unhandled exception.

### C3 — Unauthenticated financial report view
[billing/views.py:259](../billing/views.py#L259) — the `financial_report` view's auth decorator is written as a bare statement `login_required` (no `@`, no parentheses), not applied to the function below it. This is a no-op — the line does nothing. Every other view in this file uses `@login_required`, confirming this is a bug, not intentional. **The full financial report (all payments, expenses, doctor revenue, branch summaries, PDF/Excel export) is reachable by anyone, including unauthenticated visitors**, at `billing:financial_report`.

### C4 — Cross-branch IDOR on patient, appointment, payment, expense, employee records
Sequential integer PKs are used as public identifiers everywhere (`<int:pk>/` in every app's `urls.py`), and detail/update/delete views resolve them with `get_object_or_404(Model, pk=pk)` **without filtering by the requesting user's branch**, even though the equivalent *list* views do filter by branch. Confirmed instances:
- [patients/views.py:59](../patients/views.py#L59) (`patient_detail`), [:78](../patients/views.py#L78) (`patient_update`), [:100](../patients/views.py#L100) (`patient_delete`) — contrast with `patient_list` at [:42](../patients/views.py#L42) which *does* filter by `request.user.branch`.
- [appointments/views.py:75](../appointments/views.py#L75), [:87](../appointments/views.py#L87), [:110](../appointments/views.py#L110).
- [billing/views.py:52](../billing/views.py#L52) (`payment_update`), [:75](../billing/views.py#L75) (`payment_delete`), [:90](../billing/views.py#L90) (`payment_detail` — this one isn't even role-gated, only `@login_required`).
- [employees/views.py:55](../employees/views.py#L55), [:77](../employees/views.py#L77).

**Impact**: any authenticated Reception or Admin user from Branch A can view, edit, or delete a patient/appointment/payment/employee record belonging to Branch B just by changing the integer in the URL. This is real patient data (medical/contact info, national ID, payment amounts).

### C5 — Branch management has no authorization check at all
[branches/views.py:9-76](../branches/views.py#L9-L76) — `branch_create`, `branch_list`, `branch_update`, `branch_delete` are guarded only by `@login_required`. There is no role check. **Any authenticated user, including Reception staff, can create, edit, or delete any branch**, including branches they don't belong to.

---

## HIGH

### H1 — Cross-branch admin overreach in user management
[accounts/views.py:78](../accounts/views.py#L78) — `user_list` returns `User.objects.all()` with no branch scoping. [:91](../accounts/views.py#L91) `user_update` and [:115](../accounts/views.py#L115) `user_delete` resolve any user by pk with no branch check. Since the `Admin` role ([accounts/models.py:6-10](../accounts/models.py#L6-L10)) is a flat, non-branch-scoped `ClinicRole`, **any user with the Admin role at one branch can edit or delete admins/users at every other branch**, including changing their password/role/branch via `UserForm`.

### H2 — Audit log exposed to any authenticated user
[audit/views.py:6-14](../audit/views.py#L6-L14) — `audit_list` shows `AuditLog.objects.all()` (every action, every branch, every user) to anyone who is merely `@login_required`, with no role or branch filter. Combined with H1/C4, a low-privilege user can read the full activity history of the entire clinic network.

### H3 — Audit middleware never fires for the app's actual login flow
[audit/middleware.py:20-37](../audit/middleware.py#L20-L37) — `AuditMiddleware` only logs login/logout when `request.path == "/admin/login/"` or `"/admin/logout/"` (the Django admin site). But the application's real login is `accounts:login` at `/accounts/login/` ([project/settings.py:82](../project/settings.py#L82), [accounts/urls.py:10](../accounts/urls.py#L10)). **Every real user login/logout in this system goes unaudited** — this code path is dead. (Model creation/update/deletion *is* captured generically via [audit/signals.py](../audit/signals.py) `post_save`/`post_delete` signals, which do work.)

### H4 — Undefined name `Q` crashes the financial report search
[billing/views.py:9](../billing/views.py#L9) imports only `Sum, Count` from `django.db.models`, but [:307](../billing/views.py#L307) and [:314](../billing/views.py#L314) reference `Q(...)`. Any request to `financial_report` with `doctor_revenue_search` or `non_employee_search` set raises `NameError: name 'Q' is not defined` (a 500 in production since `DEBUG` should eventually be `False`).

### H5 — `settings.ADMIN_EMAIL` referenced but never defined
[reports/views.py:78](../reports/views.py#L78), [:147](../reports/views.py#L147), [:184](../reports/views.py#L184) fall back to `[settings.ADMIN_EMAIL]` when no `ReportRecipient` is active. `ADMIN_EMAIL` does not exist anywhere in [project/settings.py](../project/settings.py) (confirmed by search) — this raises `AttributeError` and aborts the daily/monthly/annual report email job whenever the recipients list is empty.

### H6 — Inconsistent authorization model (`is_superuser` vs. role field)
[services/views.py:13](../services/views.py#L13), [:47](../services/views.py#L47), [:71](../services/views.py#L71), [:89](../services/views.py#L89) gate service management on `request.user.is_superuser`, while every other app (`patients`, `appointments`, `billing`, `employees`, `branches`-should-but-doesn't) gates on `request.user.role.name`. A branch "Admin" (role-based) cannot manage services unless also flagged `is_superuser` in Django's own auth system — two parallel, disconnected permission systems exist in the same codebase.

---

## MEDIUM

### M1 — Non-atomic serial number generation
The `save()` override pattern (count existing rows for today → format `YYYYMMDD-NNN` → loop-check for collision) is duplicated across [patients/models.py:35-48](../patients/models.py#L35-L48), [appointments/models.py:31-44](../appointments/models.py#L31-L44), [employees/models.py:39-52](../employees/models.py#L39-L52), [notifications/models.py:22-35](../notifications/models.py#L22-L35). It's not wrapped in a `select_for_update()`/transaction, so two concurrent requests on the same day can both compute the same "next" serial before either saves; the `while exists()` retry loop reduces but doesn't eliminate the race (there's a window between the check and the `INSERT`).

### M2 — Migrations are not version-controlled
[.gitignore:15](../.gitignore#L15) — `*/migrations/` is excluded from git for every app. This means the schema history isn't reproducible from source control; a fresh clone can't `migrate` to the real production schema without the actual migration files, and there's no record of how the schema evolved.

### M3 — Zero real test coverage
Every app's `tests.py` is the unmodified 3-line Django scaffold stub (confirmed by line count: 3 lines in `accounts`, `appointments`, `audit`, `billing`, `branches`, `employees`, `notifications`, `patients`, `services`). No unit, integration, or permission tests exist anywhere in the project.

### M4 — Hardcoded base template values with settings fallback repeated ~40 times
Every view in every app repeats the same three-line context dict (`clinic_name`/`clinic_logo`/`footer_text` derived from `request.user.branch` with a `getattr(settings, ...)` fallback) instead of a shared context processor. Not a bug, but meaningful duplication/maintenance risk once more views are added.

---

## What's actually solid (keep, don't rewrite)

- **`audit` app's signal-based logging** ([audit/signals.py](../audit/signals.py)) is a reasonable, generic, low-maintenance pattern — a global `post_save`/`post_delete` receiver keyed off `ContentType`, correctly excludes `AuditLog`/`Session`, degrades gracefully during `migrate`/`loaddata` (catches `OperationalError`/`ProgrammingError`). Worth keeping and building on (it's missing before/after field diffs, see doc §65, but the skeleton is sound).
- **Branch-scoped list views** (`patient_list`, `appointment_list`, `payment_list`, `expense_list`, `employee_list`) correctly filter by `request.user.branch` for non-Admin roles — the pattern exists and is proven; it's just inconsistently applied to the corresponding detail/update/delete views (see C4).
- **`notification_mark_read`** ([notifications/views.py:30-31](../notifications/views.py#L30-L31)) is the one place in the codebase that correctly scopes a `get()` by both `pk` **and** `user=request.user` — this is the pattern the IDOR-affected views in C4 should be copying.
- **Auto-generated human-readable serial numbers** (`YYYYMMDD-NNN`) are a genuinely useful feature or the SaaS `Identifier Strategy` section — just needs to move off raw sequential PKs in URLs while keeping the serial as the *display* identifier, and needs the race in M1 closed.
- **`reports` app's daily/monthly/annual aggregation logic** ([reports/views.py](../reports/views.py)) already computes real revenue/expense/doctor/service breakdowns per branch — a working foundation for the doc's Analytics/Reports sections, not something to rebuild from scratch.
