# 06 — Implementation Progress

Status values: `TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`, `NEEDS_REVIEW`.

| ID | Task | Status | Notes |
|---|---|---|---|
| SEC-001 | Rotate SECRET_KEY / EMAIL_HOST_PASSWORD, move secrets to env | NEEDS_REVIEW | Code done: `project/settings.py` now reads `SECRET_KEY`, `DEBUG`, `EMAIL_*`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` via `django-environ` from `.env` (gitignored, confirmed via `git check-ignore`). New random `SECRET_KEY` generated. `.env.example` added and tracked. **Still open**: the live email password is still the leaked one until the user rotates it via cPanel and updates `.env` on every environment (local `.env` + production) |
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
| TEST-001 | Add permission/IDOR regression tests | TODO | Not started — deferred per plan to keep this diff reviewable |
| BE-004 | Shared context processor for clinic_name/logo/footer | TODO | Not started — deferred per plan, cosmetic only |

## Production-deploy caveat for INFRA-001 (read before running `migrate` on the live server)

These `0001_initial.py` migrations were generated from the **current** `models.py` files, not from whatever schema history actually produced the live production database (which had no tracked migrations at all until now). If the production DB's real schema exactly matches what's in `models.py` today, running `python manage.py migrate --fake-initial` on production will mark these as applied without re-running the `CREATE TABLE` statements, which is the correct move. If the production schema has drifted from `models.py` in any way not visible in this repo, that mismatch needs to be resolved (compare schemas, or hand-adjust the generated migration) before running `migrate` there — running a plain `migrate` on a database that already has these tables will fail with "table already exists" without `--fake-initial`.

## Resume notes

This batch was implemented 2026-09-07, following the audit in [01-system-audit.md](01-system-audit.md) and the plan in [05-implementation-master-plan.md](05-implementation-master-plan.md). Nothing was committed — all changes are in the working tree (migrations are `git add`-staged, everything else is unstaged) for the user to review with `git diff`/`git status` before deciding to commit.

**Still open before this batch is fully closed out**:
1. User rotates the live email password via cPanel and updates `.env` (SEC-001).
2. Someone verifies the freshly generated migrations against the actual production schema before running `migrate` there (INFRA-001).
3. TEST-001 and BE-004 remain, as a separate lower-priority follow-up pass.
4. Once this batch is reviewed and committed, revisit [04-target-architecture-options.md](04-target-architecture-options.md) to pick Option A/B/C for what comes next.
