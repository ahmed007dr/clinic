# 06 — Implementation Progress

Status values: `TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`, `NEEDS_REVIEW`.

| ID | Task | Status | Notes |
|---|---|---|---|
| SEC-001 | Rotate SECRET_KEY / EMAIL_HOST_PASSWORD, move secrets to env | TODO | Requires access to production env config (cPanel) to rotate the live email password — needs the user to actually change the mailbox password, not just the code |
| SEC-002 | `DEBUG` environment-driven | TODO | |
| SEC-003 | Fix `financial_report` auth + `Q` import | TODO | |
| SEC-004 | Branch-ownership checks on patient/appointment/payment/employee detail-update-delete | TODO | |
| SEC-005 | Authorization on branch create/update/delete | TODO | |
| SEC-006 | Branch-scope user management (or confirm org-wide admin is intended) | TODO | **Needs a product decision first** — see notes in 05-implementation-master-plan.md |
| SEC-007 | Branch-scope or role-restrict audit log view | TODO | |
| SEC-008 | Fix AuditMiddleware login/logout paths | TODO | |
| BE-001 | Fix `settings.ADMIN_EMAIL` reference | TODO | |
| BE-002 | Unify `is_superuser` vs. role-based authorization | TODO | |
| BE-003 | Atomic serial_number generation | TODO | |
| INFRA-001 | Track migrations in git | TODO | |
| TEST-001 | Add permission/IDOR regression tests | TODO | |
| BE-004 | Shared context processor for clinic_name/logo/footer | TODO | |

## Resume notes

This tracker was seeded 2026-09-07 from a full audit of the codebase against `doc/readme.md`'s SaaS spec — see [01-system-audit.md](01-system-audit.md) through [04-target-architecture-options.md](04-target-architecture-options.md) for the reasoning. Per doc/readme.md §94's own stop condition, no application code was changed in this pass — this is the audit + documentation deliverable only.

**Before resuming work here**: re-run `git status`/`git diff` (per doc §6/§92) to check nothing changed underneath this tracker, and confirm with the user which of [04-target-architecture-options.md](04-target-architecture-options.md)'s Option A/B/C is the actual direction — SEC-001 through TEST-001 above are valid under all three options and can start immediately, but nothing beyond this batch should be planned until that decision is made explicit.
