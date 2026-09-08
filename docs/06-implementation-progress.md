# 06 — Implementation Progress

Status values: `TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`, `NEEDS_REVIEW`.

| ID | Task | Status | Notes |
|---|---|---|---|
| SEC-001 | Rotate SECRET_KEY / EMAIL_HOST_PASSWORD, move secrets to env | DONE (local) | Code done: `project/settings.py` reads `SECRET_KEY`, `DEBUG`, `EMAIL_*`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` via `django-environ` from `.env` (gitignored, confirmed via `git check-ignore`). New random `SECRET_KEY` generated. User rotated the email account itself (new address/host/password, `support@club-ft.com` on `mail.club-ft.com`, replacing the leaked `dr-ahmed@2odays.com` credential) — local `.env` updated and verified to load correctly (`manage.py check` clean, including the `$` in the password parsing as a literal, not shell-expanded). **Still open**: the production server's own `.env` (or equivalent env config) needs the same update — this agent has no access to the live server |
| SEC-002 | `DEBUG` environment-driven | DONE | `env.bool('DJANGO_DEBUG', default=False)` — defaults safe (off) unless explicitly set |
| SEC-003 | Fix `financial_report` auth + `Q` import | DONE | `billing/views.py`: `@login_required` restored, `Q` added to the `django.db.models` import |
| SEC-004 | Branch-ownership checks on patient/payment detail views | DONE | Scope narrowed after the SEC-006 decision (Admin is intentionally org-wide, so Admin-only update/delete views needed no change): added branch checks to `patient_detail` (Reception-reachable) and `payment_detail` (previously had no role/branch gate at all) |
| SEC-005 | Authorization on branch create/update/delete | DONE | `branches/views.py`: added `@user_passes_test(is_admin)`, `branch_list` intentionally left open to any logged-in user (non-sensitive, used in dropdowns) |
| SEC-006 | Admin scope decision | DONE | User confirmed org-wide Admin is intended — no code change needed in `accounts` |
| SEC-007 | Role-restrict audit log view | DONE | `audit/views.py`: `audit_list` now Admin-only |
| SEC-008 | Fix dead login/logout audit hook | DONE | Real login/logout logging moved into `accounts/views.py` (`user_login`/`user_logout`), since `AuditMiddleware` was matching `/admin/login/`/`/admin/logout/`, not the app's real `/accounts/login/`/`/accounts/logout/` routes |
| BE-001 | Fix `settings.ADMIN_EMAIL` reference | DONE | `reports/views.py`: all 3 report generators now skip sending (instead of crashing) when there are no active `ReportRecipient`s |
| BE-002 | Unify `is_superuser` vs. role-based authorization | DONE | `services/views.py`: now checks `role.name == 'Admin'`, matching every other app |
| BE-003 | Atomic serial_number generation | DONE | `patients`, `appointments`, `employees`, `notifications` models: `save()` now wraps generation in `transaction.atomic()` + `select_for_update()` |
| INFRA-001 | Track migrations in git | NEEDS_REVIEW | Bigger than originally scoped — **this checkout had no migration files at all beyond `__init__.py`** (only those were ever tracked; the gitignore rule hid the real ones). Generated fresh `0001_initial.py` for every app using an isolated venv pinned to `Django==4.2` (matching `requirements.txt`, since the ambient `python` here is 5.2) — verified by running `migrate` end-to-end against a throwaway local DB (succeeded) and importing every edited module (no errors). Staged in git, not committed. **See the production-deploy caveat below before applying these to the real database.** |
| TEST-001 | Add permission/IDOR regression tests | DONE | 20 tests added across `patients`, `billing`, `branches`, `audit`, `services` covering every SEC-00x/BE-002 fix, run against an isolated venv pinned to `Django==4.2`. All pass (`manage.py test` — 20/20 OK), and the whole project's `manage.py check` is clean |
| BE-004 | Shared context processor for clinic_name/logo/footer | DONE | Added `utils/context_processors.py` (`clinic_branding`), registered in `TEMPLATES.OPTIONS.context_processors`; removed the duplicated 3-line dict entries from ~40 view functions across 10 apps, plus the now-unused `from django.conf import settings` import in 9 of them. As a side effect this also fixes `branches`/`audit` views, which previously ignored the logged-in user's branch entirely (always showed the settings-level default name/logo/footer even for a user with a real branch) — they now get the same branch-aware values as every other page |
| BUG-001 | Global audit signal crashed on fresh migrations | DONE | Found while getting `manage.py test` to even create a test database: `audit/signals.py`'s global `post_save`/`post_delete` receiver logged every model's own bookkeeping, including `ContentType` and the migration recorder's `Migration` model — saving either during a fresh `migrate` can raise `IntegrityError` (contenttypes' `0001_initial` creates `django_content_type` with a NOT NULL `name` column that `0002` only removes afterward) and abort the migration. Fixed by excluding `ContentType`/`Migration` from `EXCLUDED_MODELS` and widening the existing "DB not ready yet" exception guard to also catch `IntegrityError`. This is a real risk for provisioning any *fresh* environment, not just tests |
| BE-005 | Reject negative money values | DONE (see correction) | **Correction:** this was recorded as needing no migration. That was wrong — Django *does* record `validators` in migration state. The verification was faulty too: `makemigrations --check` exits silently, and the exit code being read came from the last command in a pipe rather than from Django. The missing `AlterField`s were picked up in the Step 3 migrations. Original note follows |
| BE-005 (original note) | Reject negative money values | DONE | The `forms.py` validation sweep from the original audit plan found no custom `clean()` anywhere and, more importantly, no floor on any monetary field: `Payment.amount`, `Expense.amount`, `Service.base_price`, `Employee.salary_value`, `Appointment.price` all accepted negatives, which would silently skew every total in `financial_report` and the daily/monthly report emails. Added `MinValueValidator(0)` to all five (0 still allowed — free/waived services are legitimate). No migration needed: `validators` are form/`full_clean()`-level, not schema (verified with `makemigrations --check`). 3 tests added |
| BUG-002 | Thread-local `request` never cleared → misattributed audit entries | DONE | Found via test isolation failures: `audit/middleware.py`'s `ThreadLocalMiddleware` set `_thread_locals.request` on every request but never cleared it, so on a reused worker thread (this is exactly the Passenger/cPanel deployment model) any model save happening outside a real request on that thread — a later test, a management command, a background job sharing the thread — could get attributed in `AuditLog` to whichever user's request that thread handled *last*, including a request whose user object no longer exists. Rewrote `ThreadLocalMiddleware` as modern callable middleware that clears the thread-local in a `finally` block after every request |

## Batch 2 — Multi-tenancy foundation (Option C)

Chosen 2026-09-08. Design: [07-multi-tenancy-architecture.md](07-multi-tenancy-architecture.md). Task detail: [05-implementation-master-plan.md](05-implementation-master-plan.md). Nothing started yet — no code written for this batch.

| ID | Task | Status | Notes |
|---|---|---|---|
| INFRA-002 | Move to PostgreSQL | NEEDS_REVIEW | Code done: `psycopg2-binary` added, `DATABASES` now driven by `DATABASE_URL` via `env.db()` (SQLite default only so a fresh checkout runs unconfigured), `.env.example` documents the DigitalOcean URL form including the required `?sslmode=require`. **Verified on SQLite only** — no DigitalOcean instance exists yet, and the local PostgreSQL 16/17 servers are password-protected, so nothing has been run against real PostgreSQL |
| INFRA-003 | Managed hosting + split DB roles | TODO | DigitalOcean Managed PostgreSQL chosen. Still needs the instance provisioned, the app/migration role split created, and the live data moved |
| TENANT-001 | `tenants` app + `Tenant` model | DONE | `Tenant` (uuid, name, slug, status, created_at) + `TenantOwnedModel` base; `tenants.0002` creates Tenant #1 from `settings.CLINIC_NAME` → "Dr-ahmed" / `dr-ahmed`, status active |
| TENANT-002 | `tenant` FK on all 17 models + backfill | DONE | 15 models via the base, `User` and `AuditLog` with nullable FKs. 10 hand-written `0002_add_tenant` migrations (add nullable → backfill → enforce NOT NULL), verified with `makemigrations --check` reporting no drift. **Upgrade path tested by simulation**: built the pre-tenant schema, inserted legacy rows, migrated forward — all rows backfilled to Tenant #1, zero orphans |
| TENANT-003 | Per-tenant unique constraints | DONE | 9 global `unique=True` flags replaced with `UniqueConstraint(tenant, …)` across Branch (name + code), Service, PaymentMethod, ExpenseCategory, ClinicRole, Employee (national_id), Payment (receipt_number), ReportRecipient (email), and `serial_number` on 4 models. Relaxing global → per-tenant can't invalidate existing rows, so no data fix-up was needed. Tests prove two tenants can now hold the same branch name, service name and role names, while duplicates *within* one tenant are still rejected |
| TENANT-004 | `SerialCounter` replaces count-based serials | DONE | New `SerialCounter(tenant, scope, date) → last_value` in `tenants`, locked with `select_for_update()`. The four `save()` overrides drop from ~14 lines of counting-and-retrying to one call, and the serial format now lives in one place. **`tenants.0004` seeds counters from existing serials** — without it the first insert after deploy would re-issue a number an existing row already held. Verified by simulation: 5 legacy rows for today → counter seeded to 5 → next patient issued `-006`, zero duplicates |
| TENANT-005 | contextvar + tenant middleware | TODO | |
| TENANT-006 | `TenantManager` (fails closed) | TODO | |
| TENANT-007 | PostgreSQL RLS policies | TODO | |
| TEST-002 | Cross-tenant isolation suite | TODO | |
| SEC-009 | Email login + `User.tenant` + platform staff | TODO | |
| SEC-010 | Per-tenant role seeding | TODO | |
| SEC-011 | UUID/slug public identifiers | TODO | |
| TENANT-008 | Tenant onboarding + second tenant | TODO | First live proof isolation holds |

### Found while implementing TENANT-002

Making `tenant` required surfaced four write paths that would otherwise have broken at runtime rather than at review:

1. **Two `post_migrate` seeding hooks** create tenant-owned rows — `accounts/apps.py` (Admin/Reception roles) and a second one in `employees/apps.py` seeding the "Doctor" `EmployeeType` that `Appointment.doctor` depends on via `limit_choices_to`. Both would have broken `migrate` itself. Now seed per tenant; they move into tenant provisioning at TENANT-008.
2. **`notifications/signals.py`** creates a `Notification` per user on every appointment and payment — needed the tenant threading through.
3. **11 create views** had to set `tenant` explicitly before saving. Interim by design: TENANT-005/006 will assign it automatically from request context, and these lines then get deleted.
4. **`employee_create` needed `form.save_m2m()`** once it switched to `commit=False` — without it the employee's specializations would have been silently dropped on every create.

*(Superseded by TENANT-003 below, which removed the global unique constraints that made those seeding hooks single-tenant-only. One correction to an earlier note here: `EmployeeType.name` was never globally unique — only `ClinicRole.name` was.)*

## Production-deploy caveat for INFRA-001 (read before running `migrate` on the live server)

These `0001_initial.py` migrations were generated from the **current** `models.py` files, not from whatever schema history actually produced the live production database (which had no tracked migrations at all until now). If the production DB's real schema exactly matches what's in `models.py` today, running `python manage.py migrate --fake-initial` on production will mark these as applied without re-running the `CREATE TABLE` statements, which is the correct move. If the production schema has drifted from `models.py` in any way not visible in this repo, that mismatch needs to be resolved (compare schemas, or hand-adjust the generated migration) before running `migrate` there — running a plain `migrate` on a database that already has these tables will fail with "table already exists" without `--fake-initial`.

## Resume notes

This batch was implemented 2026-09-07, following the audit in [01-system-audit.md](01-system-audit.md) and the plan in [05-implementation-master-plan.md](05-implementation-master-plan.md), across two passes: the initial SEC-00x/BE-00x/INFRA-001 fixes, then a follow-up (TEST-001, BE-004) that also surfaced and fixed BUG-001/BUG-002 above. Partway through, a commit titled "progress" (651fdac) was made from the editor — not by this agent — capturing an intermediate snapshot (the first pass plus a couple of in-progress test files). The working tree as it stands now is the complete, fully-tested state; nothing further has been committed on top of it.

**Still open before this batch is fully closed out**:
1. Apply the same new email credentials to the production server's `.env` (SEC-001) — done locally, still needed on the live host.
2. Someone verifies the freshly generated migrations against the actual production schema before running `migrate` there (INFRA-001).
3. Once this batch is reviewed and committed, revisit [04-target-architecture-options.md](04-target-architecture-options.md) to pick Option A/B/C for what comes next.
