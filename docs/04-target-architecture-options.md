# 04 — Target Architecture Options

`doc/readme.md` describes one target: a full multi-tenant SaaS platform across 36 phases. Given the gap documented in [02-current-architecture.md](02-current-architecture.md) and [03-domain-model.md](03-domain-model.md), that's a real, multi-quarter engineering program, not an incremental change to the current app. Before committing engineering time, it's worth choosing a target deliberately rather than assuming the maximal one. Three options, honestly compared:

## Option A — Harden the current single-organization app

**What it means**: keep the Django-templates, multi-branch (single-organization) architecture as-is. Fix the audit findings (IDOR, unauthenticated view, missing decorators, undefined names, secret rotation, migrations tracking, tests). Add real branch-scoped permission checks consistently. No new domains beyond what exists.

**When this is right**: if this system serves one clinic organization (with its branches) and there's no near-term plan to sell it to other clinics as a product.

**Effort**: small — days, not months. Directly maps to the `05-implementation-master-plan.md` SEC/BE task list already seeded from this audit.

**Trade-off**: doesn't move toward doc/readme.md's SaaS vision at all — if that's a real business goal, this is deferred work, not skipped work.

## Option B — Add an API layer + incremental modernization, still single-organization

**What it means**: Option A's fixes, plus introduce Django REST Framework alongside (not replacing) the existing template views, so a future frontend (React or otherwise) or mobile app can be built without a full rewrite. Add the missing clinical domain (medical records/prescriptions) if that's actually needed, add proper pricing/invoicing if billing needs to grow beyond flat prices. Still one organization, still `Branch` as the isolation unit — no `Tenant` layer.

**When this is right**: if there's a concrete need for a patient-facing portal, mobile app, or richer clinical workflow, but still for this one clinic operation — not a multi-tenant product.

**Effort**: medium — multiple weeks per domain added (API layer, then each new domain: medical records, pricing, invoicing).

**Trade-off**: still doesn't add multi-tenancy; if the goal really is "sell this to other clinics," this path still needs a second, disruptive migration later to introduce `Tenant`.

## Option C — Full SaaS transformation per doc/readme.md

**What it means**: everything in doc/readme.md — introduce `Tenant`/`Organization` above `Branch`/`Clinic`, subscriptions and plans, DRF API, React frontend, payment gateway integration, pricing/contract/commission engine, financial ledger, patient/doctor/clinic-admin/SaaS-admin portals, and eventually the optional blockchain-integrity and AI features. Phased per the doc's own §89 (Phase 0 through 36).

**When this is right**: if the actual goal is to turn this into a product sold to multiple independent clinic businesses, not just serve the current one.

**Effort**: large — this is a from-scratch product build reusing only the domain concepts (not much of the current code) documented in 02/03. Realistically many months across backend, frontend, security, and QA, even executed phase-by-phase per the doc's own task-ID system.

**Trade-off**: the biggest one — this is the only option that fulfills doc/readme.md's literal ask, but it means this specific production system (with real patient data, currently unhardened per [01-system-audit.md](01-system-audit.md)) has to be secured *first* regardless of which option is chosen, before any months-long rebuild starts on top of it.

## Recommendation

Independent of which of A/B/C is chosen, the CRITICAL and HIGH items in [01-system-audit.md](01-system-audit.md) (leaked secrets, the unauthenticated financial report, the cross-branch IDOR, the branch-management auth gap) affect real patient/financial data *today* and should be fixed first as their own small, fast batch — this is Option A's task list, and it's a strict subset of what B and C need anyway. Which of A/B/C to pursue afterward is a business decision (is this becoming a multi-clinic product, or does it stay this one organization's internal system?) that should be made explicitly rather than defaulted into.

## Decision — 2026-09-08

**Option C (full SaaS transformation) was chosen.** The Option A hardening batch it depends on is complete (all audit findings fixed, tested, committed — see [06-implementation-progress.md](06-implementation-progress.md)).

Three architecture decisions were taken alongside it: PostgreSQL on a managed host (leaving cPanel), the live clinic migrating in place as Tenant #1, and one-tenant-per-user with email as the login. The design that follows from those is in [07-multi-tenancy-architecture.md](07-multi-tenancy-architecture.md), and the task breakdown is in [05-implementation-master-plan.md](05-implementation-master-plan.md).
