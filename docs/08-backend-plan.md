# 08 — Backend Plan

Status of the backend, and what is left. Companion to [09-frontend-plan.md](09-frontend-plan.md).

Markers: **Done** · **Partial** · **Parked** (deferred by decision) · **Not started**

Stack today: Django 4.2, server-rendered, SQLite in development, no API layer. 109 tests. Full task history in [06-implementation-progress.md](06-implementation-progress.md).

---

## 1. Security and correctness of the existing system — **Done**

Everything found in [01-system-audit.md](01-system-audit.md) is fixed and covered by tests.

| ID | Item | Status |
|---|---|---|
| SEC-001/002 | Secrets out of git into env; `DEBUG` env-driven; credentials rotated | **Done** |
| SEC-003 | `financial_report` was reachable without login (broken decorator) | **Done** |
| SEC-004 | Cross-branch data leak on patient and payment records | **Done** |
| SEC-005 | Branch management had no authorization at all | **Done** |
| SEC-006 | Org-wide Admin confirmed as intended | **Done** |
| SEC-007 | Audit log was readable by any logged-in user | **Done** |
| SEC-008 | Login/logout were never audited (dead middleware path) | **Done** |
| BE-001 | Report job crashed on an undefined setting | **Done** |
| BE-002 | Two parallel permission systems unified onto roles | **Done** |
| BE-003 | Serial-number generation made atomic | **Done** |
| BE-004 | Shared context processor | **Done** |
| BE-005 | Negative amounts rejected on all money fields | **Done** |
| BUG-001 | Audit signal aborted fresh migrations | **Done** |
| BUG-002 | Thread-local leak misattributed audit entries | **Done** |
| INFRA-001 | Migrations brought under version control | **Done** |
| TEST-001 | Permission/IDOR regression suite | **Done** |

---

## 2. Multi-tenancy foundation — **Done** (except the database layer)

Design: [07-multi-tenancy-architecture.md](07-multi-tenancy-architecture.md).

| ID | Item | Status |
|---|---|---|
| TENANT-001 | `Tenant` model, Tenant #1 created from existing data | **Done** |
| TENANT-002 | `tenant` on all 17 models + backfill migrations | **Done** |
| TENANT-003 | 9 global unique constraints became per-tenant | **Done** |
| TENANT-004 | `SerialCounter` replaced count-based serials | **Done** |
| TENANT-005 | `contextvars` + middleware, tenant from session only | **Done** |
| TENANT-006 | `TenantManager` fails closed; `all_objects` escape hatch | **Done** |
| TEST-002 | Cross-tenant isolation suite | **Done** |
| SEC-009 | Email login, `User.tenant`, `is_platform_staff` | **Done** |
| SEC-010 | Tenant provisioning as single source of truth | **Done** |
| SEC-011 | UUID public identifiers on all 26 routes | **Done** |
| TENANT-008 | `create_tenant` onboarding, proved with a real third clinic | **Done** |
| INFRA-002 | PostgreSQL config (`DATABASE_URL`, psycopg2) | **Partial** — code only, never run against PostgreSQL |
| INFRA-003 | DigitalOcean instance, split app/migration DB roles | **Parked** |
| TENANT-007 | PostgreSQL row-level security policies | **Parked** |

> **The one open risk.** Isolation currently rests on three application-level layers. The database-level backstop (RLS) is the layer designed to catch what the others miss, and it is not in place. Three times this session the fail-closed manager went silently wrong in a new disguise — empty form dropdowns, reverse accessors, the allergy safety check. Each was caught by building something new, not by a test.

---

## 3. Clinical domain — **Partial**

| ID | Item | Status |
|---|---|---|
| MED-001 | `Visit` (complaint, examination, diagnosis, plan, follow-up) | **Done** |
| MED-002 | Clinical access control — Reception excluded, `Doctor` role | **Done** |
| MED-003 | Medical retention — records `PROTECT` patient deletion | **Done** |
| MED-005 | `Prescription` + items, inline formset, printable sheet | **Done** |
| MED-006 | Non-blocking allergy conflict warning | **Done** |
| MED-007 | Procedures performed during a visit | **Not started** |
| MED-008 | Lab results | **Not started** |
| MED-009 | File attachments — scans, reports (doc §61 security rules apply: MIME + extension validation, size limits, authorization on every download, signed URLs) | **Not started** |
| MED-010 | **Treatment plans and sessions** (doc §28) — a course of N sessions, each with date, doctor, service, quantity, price, payment, result | **Not started** |
| MED-011 | Quantity/pulse-based services (doc §29 — laser priced per pulse) | **Not started** |
| MED-012 | Clinical templates per specialty (doc §24) | **Not started** |
| MED-013 | Custom dynamic forms (doc §25) | **Not started** |

> **MED-010 is the commercially significant gap.** The system cannot currently represent "12 laser sessions paid up front" — which is how the laser side of this business actually operates. It also blocks correct revenue recognition, because money is taken once and delivered over months.

---

## 4. Financial and commercial — **Not started**

The current billing app records flat payments and expenses. None of the below exists.

| ID | Item | Notes |
|---|---|---|
| FIN-001 | Pricing engine (doc §30) | No hardcoded prices; price resolved from clinic + doctor + service + contract + quantity + date + promotion |
| FIN-002 | Contracts (doc §31) | Per doctor/clinic relationship: dates, pricing, commission, services |
| FIN-003 | Commissions (doc §32) | Percentage/fixed/tiered — **must snapshot rate at transaction time** so later contract changes never rewrite history |
| FIN-004 | Invoices (doc §33) | Line items, discount, tax, gross/net, paid/remaining, refunds — distinct from today's flat `Payment` |
| FIN-005 | Payment providers (doc §34/35) | Paymob/Fawry behind an abstraction; webhook + signature verification; frontend never decides success |
| FIN-006 | Financial ledger (doc §36) | Immutable movements, not live aggregation over `Payment`/`Expense` |
| FIN-007 | Reconciliation (doc §82) | Detect missing, duplicate, failed, mismatched-amount payments |
| FIN-008 | Packages and promotions (doc §40/41) | Priced through the pricing engine |

---

## 5. SaaS business layer — **Not started**

Meaningful only now that a second tenant is real (TENANT-008).

| ID | Item |
|---|---|
| SAAS-001 | Plans and subscriptions — monthly/quarterly/yearly/custom (doc §11) |
| SAAS-002 | Feature entitlements per plan/tenant (doc §84) |
| SAAS-003 | SaaS admin portal — create/approve/suspend tenants, monitor revenue (doc §10) |
| SAAS-004 | Subscription billing and dunning |
| SAAS-005 | Support impersonation — explicit, time-limited, fully audited (doc §64) |
| SAAS-006 | Platform analytics: MRR, ARR, churn, active clinics (doc §47) |

---

## 6. Scheduling and operations — **Partial**

| ID | Item | Status |
|---|---|---|
| OPS-001 | Appointments CRUD | **Done** (pre-existing) |
| OPS-002 | Waiting list | **Partial** — a filtered list, not a queue |
| OPS-003 | Queue engine (doc §21) — position, estimated wait, priority, no-show | **Not started** |
| OPS-004 | Double-booking prevention (doc §20) — nothing stops it today | **Not started** |
| OPS-005 | Doctor availability: working hours, breaks, holidays, per-clinic schedules (doc §16) | **Not started** |
| OPS-006 | Resource scheduling — rooms, machines (doc §39/83) | **Not started** |
| OPS-007 | Waitlist with cancellation notifications (doc §22) | **Not started** |
| OPS-008 | Doctors working across multiple clinics (doc §15) — `Employee.branch` is a single FK today | **Not started** |
| OPS-009 | Link `User` ↔ `Employee` — a doctor account and a doctor record are unrelated objects today | **Not started** |

---

## 7. Platform services — **Partial**

| ID | Item | Status |
|---|---|---|
| PLAT-001 | Audit logging | **Done** — generic signals, now tenant-aware |
| PLAT-002 | Audit before/after field diffs (doc §65) | **Not started** |
| PLAT-003 | Notifications — in-app | **Done** (pre-existing) |
| PLAT-004 | Email/SMS/WhatsApp channels behind one interface (doc §44/45) | **Not started** |
| PLAT-005 | Background jobs (doc §71) — reports, reminders, exports currently have no scheduler | **Not started** |
| PLAT-006 | Scheduled report delivery — the generators exist but nothing invokes them | **Not started** |
| PLAT-007 | Search with proper indexes and debouncing (doc §70) | **Not started** |
| PLAT-008 | Backup, restore and restore *testing* (doc §78) | **Not started** |
| PLAT-009 | Rate limiting, security headers, CORS/CSRF hardening (doc §75) | **Not started** |
| PLAT-010 | Performance baseline: N+1 audit, indexes, pagination (doc §67/68) | **Not started** |

---

## 8. API layer — **Not started**

No REST framework is installed. This gates the frontend decision in [09-frontend-plan.md](09-frontend-plan.md).

| ID | Item |
|---|---|
| API-001 | Install and configure DRF alongside the existing template views |
| API-002 | Token/JWT auth carrying tenant context |
| API-003 | Serializers exposing `uuid`, never integer PKs (doc §51) |
| API-004 | Tenant scoping on every viewset — the manager already provides it, but it must be verified per endpoint |
| API-005 | Versioning, pagination, throttling |
| API-006 | OpenAPI schema |

---

## Recommended order

1. **Un-park PostgreSQL and RLS** (INFRA-002/003, TENANT-007). Everything built on top compounds the cost of finding an isolation flaw later, and RLS is the layer meant to catch what the app misses.
2. **MED-010 treatment plans and sessions** — the largest functional gap against how the business actually runs.
3. **FIN-001/004/006 pricing, invoices, ledger** — sessions and packages need real pricing behind them, and revenue recognition depends on it.
4. **API-001..004** once the domain is stable, since the API surface should not be built twice.
5. **SAAS-001/002** plans and entitlements, then the operator portal.

Queue/availability (OPS-003..006) can proceed in parallel — it touches scheduling and little else.
