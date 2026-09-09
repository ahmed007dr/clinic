# 02 — Current Architecture (as it actually exists)

## Stack

| Layer | Reality |
|---|---|
| Framework | Django 4.2, server-rendered (Django Templates + `django.contrib.messages`), **not** a REST API |
| Frontend | None — no React/Vue/SPA anywhere in this repo. UI is Django templates under each app's `templates/` plus a shared `templates/` at project root |
| Database | SQLite (`project/settings.py:112`), single file, no read replicas, no connection pooling config |
| Auth | Django's built-in session auth (`django.contrib.auth`) with a custom `AUTH_USER_MODEL = "accounts.User"` |
| API layer | None — no Django REST Framework in `requirements.txt`, no JWT, no API versioning |
| Multi-tenancy | None — single Django project/database serving one clinic organization ("Dr-ahmed") with multiple **branches** (physical locations), not multiple tenant organizations |
| Deployment | **Unknown / none reachable.** `passenger_wsgi.py` is present but entirely commented out (since 2025-09-29), and `2odays.com` no longer resolves. No Passenger config (`.htaccess`) has ever been tracked here, so any production configuration lives outside this repository. Originally recorded as Passenger/cPanel shared hosting; withdrawn — see [01-system-audit.md](01-system-audit.md) and the Gate A findings in [06-implementation-progress.md](06-implementation-progress.md) |
| Background jobs | None — no Celery/RQ/cron abstraction in code; `reports/views.py`'s `generate_daily_report()` etc. look like they're meant to be invoked by an external cron job hitting a management command or scheduled task, but no such command exists in the apps read so far |
| Payments | None — no payment gateway integration (Paymob/Fawry/etc.); `billing` records payments/expenses manually entered by staff, cash-register style |
| Email | SMTP via `django.core.mail`, configured directly in `settings.py` (see [01-system-audit.md](01-system-audit.md) C1) |

## Request flow

```
Browser
 → Django URL router (project/urls.py)
 → app urls.py (namespaced per app: accounts, patients, appointments, billing, branches, employees, notifications, audit, services, dashboard)
 → function-based view (all views are FBVs with @login_required / @user_passes_test decorators — no CBVs, no DRF viewsets)
 → forms.py (Django ModelForm) for validation
 → models.py (Django ORM, SQLite)
 → Django template rendered server-side
 → HTTP response
```

Middleware stack ([project/settings.py:61-73](../project/settings.py#L61-L73)): standard Django security/session/CSRF/auth/messages/clickjacking middleware, plus two custom ones from the `audit` app — `ThreadLocalMiddleware` (stashes `request` in thread-local storage so signal handlers can access it) and `AuditMiddleware` (see [01-system-audit.md](01-system-audit.md) H3 for its gap).

## Installed apps and what each owns

| App | Owns | Notable |
|---|---|---|
| `accounts` | Custom `User` (extends `AbstractUser`) + `ClinicRole` | Role is a flat FK (`Admin`, `Reception`, ...), not branch-scoped |
| `branches` | `Branch` (physical clinic location: name, code, address, logo, footer text) | This is the closest existing concept to a "tenant boundary" today — see [03-domain-model.md](03-domain-model.md) |
| `employees` | `Employee`, `EmployeeType`, `Specialization`, `SalaryType` | Employee (including doctors) belongs to exactly one `Branch` — no multi-branch doctor support yet (doc §15 asks for this) |
| `patients` | `Patient` | Belongs to one `Branch` |
| `services` | `Service` (name, price, specialization) | Flat price, no per-branch/per-doctor pricing (doc §30's "Pricing Engine" doesn't exist) |
| `appointments` | `Appointment` (patient, doctor, service, status, branch, scheduled_date, price) | Status choices are reception-workflow-specific (`entered`/`waiting`/`called`/`quick`), not the fuller lifecycle in doc §20 |
| `billing` | `Payment`, `PaymentMethod`, `Expense`, `ExpenseCategory` + the `financial_report` view | Manual entry, no gateway, no invoice model, no ledger |
| `notifications` | `Notification` (in-app only) | No email/SMS/WhatsApp dispatch tied to it despite the `type` choices suggesting it |
| `audit` | `AuditLog` + middleware/signals | Generic create/update/delete logging works; login/logout logging doesn't (see H3) |
| `reports` | `ReportRecipient` + daily/monthly/annual email report generators | Aggregation logic is real and reusable; delivery mechanism (what triggers these functions) wasn't found in the apps read |
| `dashboard` | Single `dashboard` view aggregating today's stats + 7-day trend | Admin sees 7-day trend arrays, Reception sees only today's totals |
| `utils` | `export_pdf`, `export_excel` shared helpers (`reportlab`, `openpyxl`) | Used by patients/billing/services export views |

## Identity boundary today

There is **no tenant model**. The unit of data isolation the app actually tries to enforce (inconsistently — see audit C4/C5/H1) is `Branch`. All branches belong to the same single organization/database. This means:
- Today's "multi-branch" is roughly analogous to doc/readme.md's `Clinic` level, not its `Tenant`/SaaS level.
- There is no `Organization`/`Tenant` concept above `Branch` at all — introducing one is a schema-level, not just a naming, change.

## Reusable foundations (per doc §2 — don't rewrite what's good)

- Django's session auth + custom `User`/`ClinicRole` — solid starting point for RBAC, just needs branch-scoping fixed (H1) and permission-object checks added (currently role-name string comparisons scattered across every view, e.g. `user.role.name == 'Admin'`).
- `Branch` as the existing scoping concept — can become the `Clinic` in a future tenant hierarchy without a rename, just by adding a `Tenant`/`Organization` FK above it.
- The `audit` signal-based logging skeleton.
- The `reports` aggregation functions (revenue/expenses/doctor/service breakdowns).
- `utils/export_pdf` / `utils/export_excel` — generic, reusable, not tied to one model.
- The branch-scoped *list* view pattern (needs to be applied to detail/update/delete too).
