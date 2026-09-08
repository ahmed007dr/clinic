# 05 — Implementation Master Plan

Task IDs per doc/readme.md §4 convention. This batch covers **only** the audit-derived fixes (Option A from [04-target-architecture-options.md](04-target-architecture-options.md)) — these are the concrete, unambiguous tasks regardless of which longer-term option gets chosen next. Further batches (BE-1xx for Option B domains, or the full phase list for Option C) get appended here once a direction is confirmed, not written speculatively now.

| ID | Task | Source finding | Notes |
|---|---|---|---|
| SEC-001 | Rotate `SECRET_KEY` and `EMAIL_HOST_PASSWORD`; move both + all other settings-file secrets to environment variables via the already-installed `django-environ` | C1 | Must assume git history is already exposed — rotate, don't just relocate |
| SEC-002 | Make `DEBUG` environment-driven (`env.bool("DEBUG", default=False)`), confirm production deploys with it off | C2 | |
| SEC-003 | Fix `financial_report`'s missing `@login_required` and add proper role/branch scoping to match the rest of `billing` | C3, H4 | Also fixes the `Q` `NameError` (H4) by adding the missing import while touching this view |
| SEC-004 | Add branch-ownership checks to `patient_detail/update/delete`, `appointment_detail/update/delete`, `payment_detail/update/delete`, `employee_update/delete` — mirror the filtering already correct in the corresponding list views | C4 | Use `notification_mark_read`'s `get(pk=pk, user=request.user)` pattern as the template — same idea, scoped by branch instead of user |
| SEC-005 | Add role-based authorization to `branch_create/update/delete` (currently `@login_required` only) | C5 | |
| SEC-006 | Branch-scope `user_list`/`user_update`/`user_delete` in `accounts` so an Admin can only manage users within their own branch, or explicitly define a separate "org-wide admin" role if that's intended | H1 | Needs a product decision: are branch Admins supposed to manage other branches or not? |
| SEC-007 | Branch-scope `audit_list`, or restrict it to Admin role at minimum | H2 | |
| SEC-008 | Fix `AuditMiddleware` to hook the real `accounts:login`/`accounts:logout` views instead of the unused `/admin/login/`/`/admin/logout/` paths | H3 | |
| BE-001 | Fix `settings.ADMIN_EMAIL` reference in `reports/views.py` (define it in settings, or handle the empty-recipients case without a hard settings dependency) | H5 | |
| BE-002 | Unify the authorization model: replace `services`' `is_superuser` checks with the same `role.name` pattern used everywhere else (or vice versa — pick one and apply consistently) | H6 | |
| BE-003 | Wrap the `serial_number` generation `save()` overrides in `transaction.atomic()` + `select_for_update()` (or switch to a DB-level sequence/constraint) to close the race window | M1 | Same fix applies to all 4 duplicated implementations (patients, appointments, employees, notifications) |
| INFRA-001 | Track `*/migrations/` in git (remove the blanket exclusion in `.gitignore`, commit the current migration state) | M2 | |
| TEST-001 | Add real test coverage starting with the views touched by SEC-003 through SEC-007 (permission/IDOR regression tests are the highest-value tests given the findings) | M3 | |
| BE-004 | Extract the repeated `clinic_name`/`clinic_logo`/`footer_text` context dict into a shared context processor | M4 | Low priority, cleanup only |

## Sequencing

1. SEC-001, SEC-002 first and independently — these are config-only changes, no code paths depend on them, and they address the most exposed risk (leaked live credentials).
2. SEC-003 through SEC-008 next, as a batch — same shape of fix (authorization), can be reviewed together, each is a small diff to one view file.
3. BE-001, BE-002 — independent small bug fixes, no ordering dependency.
4. BE-003, INFRA-001 — slightly larger, touch `save()` methods and repo history handling respectively; do after the security batch is merged so they don't conflict.
5. TEST-001 — write regression tests alongside or immediately after SEC-003–008 so the fixes are verifiable and don't regress.
6. BE-004 — cosmetic, do whenever convenient.

No task in this batch requires choosing between Option A/B/C — start here regardless, then use [06-implementation-progress.md](06-implementation-progress.md) to track it.

---

# Batch 2 — Multi-tenancy foundation (Option C)

Design and rationale: [07-multi-tenancy-architecture.md](07-multi-tenancy-architecture.md). Batch 1 above is complete, which is the precondition for starting this one.

Steps 0–5 (INFRA-002 → SEC-010) are **invisible to the current clinic** — the system keeps behaving exactly as it does today with a single tenant. The first behavioural change for real users arrives at TENANT-008.

| ID | Task | Step | Notes |
|---|---|---|---|
| INFRA-002 | Move to PostgreSQL — env-driven `DATABASES`, dump/load the live SQLite data, re-verify the 23 existing tests | 0 | Prerequisite for RLS. Also makes BE-003's `select_for_update()` real — it is silently ignored by SQLite today |
| INFRA-003 | Move hosting off cPanel/Passenger to a managed host; provision a non-superuser, non-`BYPASSRLS` app DB role plus a separate privileged migration role | 0 | The role split is what makes Layer 1 trustworthy |
| TENANT-001 | New `tenants` app; `Tenant` model (uuid, name, slug, status); create Tenant #1 = current clinic | 1 | Nothing references it yet — zero risk |
| TENANT-002 | `TenantOwnedModel` base + `tenant` FK on all 17 models + data migration backfilling every row to Tenant #1 | 2 | Largest schema change in the batch; still single-tenant so behaviour is unchanged |
| TENANT-003 | Convert 9 global unique constraints to per-tenant `UniqueConstraint`s | 3 | Closes the uniqueness-probing information leak |
| TENANT-004 | `SerialCounter` model; replace count-based `serial_number` generation in 4 models | 3 | Fixes a cross-tenant metrics leak, a real race, and an O(n)-per-insert cost at once |
| TENANT-005 | `contextvars`-based current-tenant + middleware resolving tenant from `request.user` only | 4 | Must not repeat BUG-002's stale thread-local; never trust client-supplied tenant |
| TENANT-006 | `TenantManager` as default `objects` (fails closed via `.none()`), unfiltered `all_objects` for platform staff | 4 | Leave `_base_manager` unfiltered or FK traversal breaks |
| TENANT-007 | PostgreSQL RLS policies on every tenant table (`ENABLE` + `FORCE`), transaction-local `set_config` | 4 | The backstop that survives a forgotten filter |
| TEST-002 | Cross-tenant isolation suite — every tenant-owned model, every URL, read/update/delete all 404 for the wrong tenant | 4 | Extends the existing 23 tests; this is what prevents an IDOR regression |
| SEC-009 | Email as `USERNAME_FIELD`, `User.tenant`, `is_platform_staff` flag | 5 | |
| SEC-010 | Move `Admin`/`Reception` seeding from the global `post_migrate` hook into per-tenant provisioning | 5 | Otherwise every deploy creates orphan global roles |
| SEC-011 | UUID/slug public identifiers replacing `<int:pk>` across all URLs, views, templates (doc §49/§50) | 6 | Do before the URL surface grows further |
| TENANT-008 | Tenant signup + provisioning (seed roles, first branch); onboard a real second tenant | 7 | First live proof the isolation holds |

**Not yet scheduled** — only meaningful after TENANT-008: plans and subscriptions (doc §11), entitlements/feature flags (§84), SaaS admin portal (§10), billing and payment-provider integration (§34–36), patient portal (§17), and the clinical domain that does not exist yet at all — medical records, prescriptions, treatment plans (§23–28).
