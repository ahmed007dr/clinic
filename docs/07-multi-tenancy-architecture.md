# 07 — Multi-Tenancy Architecture (Option C, Phase 0/1)

Design for introducing a `Tenant` layer above `Branch`, per [04-target-architecture-options.md](04-target-architecture-options.md) Option C and `doc/readme.md` §10.

## Decisions taken (2026-09-08)

| Decision | Choice | Consequence |
|---|---|---|
| Database | **PostgreSQL on a managed host** | Unlocks row-level security (the isolation backstop below) and real write concurrency. Requires leaving cPanel/Passenger. |
| Live data | **Migrate in place — current clinic becomes Tenant #1** | One continuous system, shipped incrementally. Steps 0–5 below are invisible to today's users. |
| Login | **One tenant per user, email as the login** | `User` gains a `tenant` FK; `USERNAME_FIELD` becomes email. No subdomain infrastructure needed yet. |

## Target hierarchy

```
Tenant ......... the paying customer — one clinic business
  ├── Branch ... physical location (doc/readme.md calls this "Clinic")
  │     └── Users · Employees · Patients · Appointments · Payments · Expenses
  └── tenant-level reference data
        Service · PaymentMethod · ExpenseCategory · ClinicRole
        Specialization · EmployeeType · SalaryType · ReportRecipient
```

**Naming: keep `Branch`, don't rename it to `Clinic`.** `doc/readme.md` uses "Clinic" for this layer, but the code, 40+ views, templates, and tests all say `Branch`. A rename is pure churn on a live system with zero functional benefit — treat "Clinic" as the UI label and leave the Python/DB name alone.

```python
class Tenant(models.Model):
    uuid       # public identifier — never expose the integer pk
    name       # business/legal name
    slug       # unique; future subdomain and URL segment
    status     # trial | active | suspended | cancelled  (doc §10)
    created_at
    # plan/subscription fields arrive in a later phase — not now
```

## Which models get a `tenant` FK

All 17 non-`Tenant` models are tenant-owned. **None are legitimately global.** Today only 6 have any scoping at all:

| Model | Scoping today | Notes for the migration |
|---|---|---|
| `Branch` | none (global) | Becomes the direct child of `Tenant` |
| `User` | `branch` FK, nullable | Plus `tenant`; nullable only for platform staff (see Auth) |
| `Employee` | `branch` FK, required | |
| `Patient` | `branch` FK, nullable | |
| `Appointment` | `branch` FK, nullable | |
| `Payment` | `branch` FK, nullable | |
| `Expense` | `branch` FK, required | |
| `Service` | none (global) | Tenant business data — pricing must not be shared |
| `PaymentMethod` | none (global) | |
| `ExpenseCategory` | none (global) | |
| `ClinicRole` | none (global) | Seeding must move from `post_migrate` to tenant provisioning |
| `Specialization` | none (global) | |
| `EmployeeType` | none (global) | |
| `SalaryType` | none (global) | |
| `ReportRecipient` | none (global) | Who receives a tenant's financial reports — leaks across tenants today |
| `Notification` | `user` FK only | |
| `AuditLog` | `user` FK, **nullable** | Cannot derive tenant when user is null — needs its own FK |

### Put `tenant` on every table, denormalized

Rather than deriving tenant by walking `→ branch → tenant`:

- **Row-level security requires it.** An RLS policy has to read a column on the table itself; policies that walk a three-table join are unusable in practice. This is the deciding argument.
- Single indexed column → isolation costs one predicate, no joins.
- `AuditLog` (nullable user) and `Service` (no branch at all) have no derivation path anyway.

```python
class TenantOwnedModel(models.Model):
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.PROTECT, related_name='+')
    class Meta:
        abstract = True
```

`PROTECT`, not `CASCADE`: deleting a tenant must never silently cascade away medical and financial records. Tenant offboarding is a deliberate, audited, export-then-delete process (doc §87).

15 models inherit this base. Two carry the FK directly because theirs must stay **nullable**: `User` (null = platform staff, who legitimately span tenants) and `AuditLog` (null = a platform-level event belonging to no tenant, such as creating a Tenant itself).

The cost is redundancy — `obj.tenant` must always equal `obj.branch.tenant`. Enforce with a `save()`/`clean()` guard on the base class plus a test; a DB trigger is available later if that proves insufficient.

## Isolation: four layers, because developer discipline demonstrably fails

The audit found **five** places where a developer forgot `.filter(branch=…)` and leaked data across branches ([01-system-audit.md](01-system-audit.md) C4/C5/H1). That is the empirical case for making isolation structural rather than remembered. Same failure at tenant level is a HIPAA-class breach between unrelated businesses.

**Layer 1 — PostgreSQL row-level security (the backstop).**

```sql
ALTER TABLE patients_patient ENABLE ROW LEVEL SECURITY;
ALTER TABLE patients_patient FORCE  ROW LEVEL SECURITY;   -- also binds the table owner
CREATE POLICY tenant_isolation ON patients_patient
    USING (tenant_id = current_setting('app.current_tenant_id', true)::bigint);
```

Set per transaction, never per connection:

```python
cursor.execute("SELECT set_config('app.current_tenant_id', %s, true)", [str(tenant.id)])
```

The trailing `true` makes the setting **transaction-local**, so it cannot bleed into the next request on a pooled connection — the same failure mode as the thread-local leak fixed in BUG-002 this session, avoided by construction. `current_setting(…, true)` returns NULL when unset, and `tenant_id = NULL` matches nothing, so an unset tenant **fails closed**.

Operational requirement: the Django database role must be neither superuser nor `BYPASSRLS`, or every policy is silently ignored. Migrations run as a separate privileged role.

**Layer 2 — tenant-scoped ORM manager.**

```python
class TenantManager(models.Manager):
    def get_queryset(self):
        tenant = get_current_tenant()
        qs = super().get_queryset()
        return qs.filter(tenant=tenant) if tenant else qs.none()   # fail closed
```

Note `.none()`, not unfiltered — absence of tenant context returns nothing rather than everything. Keep an explicit unfiltered `all_objects` manager for platform staff and management commands, and leave Django's `_base_manager` unfiltered (it is used internally for FK traversal; filtering it breaks related-object loading).

**Layer 3 — request context via `contextvars`, resolved from the session.**

`contextvars.ContextVar` (not a module-level thread-local) set in middleware and reset in a `finally` block — async-safe and immune to the cross-request leak we hit in BUG-002.

The current tenant is derived from `request.user.tenant`. **Never** from a header, query parameter, or URL segment supplied by the client — that would make tenant switching a one-line attack.

**Layer 4 — a cross-tenant test suite.**

A parametrised test that walks every registered tenant-owned model and asserts Tenant B receives 404 on read, update, and delete of a Tenant A object through each URL. This extends the 23 tests already in place and is what stops a regression back into the IDOR class.

## Constraints that must become per-tenant

Every global `unique=True` below is both a functional blocker (Tenant B cannot create a service named "Consultation" because Tenant A did) and an **information leak** — Tenant B can probe for the existence of a value inside Tenant A by watching which inserts get rejected as duplicates.

| Field | Today | Becomes |
|---|---|---|
| `Branch.name`, `Branch.code` | globally unique | `UniqueConstraint(tenant, …)` |
| `Service.name` | globally unique | `UniqueConstraint(tenant, name)` |
| `PaymentMethod.name` | globally unique | `UniqueConstraint(tenant, name)` |
| `ExpenseCategory.name` | globally unique | `UniqueConstraint(tenant, name)` |
| `ClinicRole.name` | globally unique | `UniqueConstraint(tenant, name)` |
| `Employee.national_id` | globally unique | `UniqueConstraint(tenant, national_id)` |
| `Payment.receipt_number` | globally unique | `UniqueConstraint(tenant, receipt_number)` |
| `ReportRecipient.email` | globally unique | `UniqueConstraint(tenant, email)` |
| `serial_number` on Patient / Appointment / Employee / Notification | globally unique | `UniqueConstraint(tenant, serial_number)` |
| `User.username` | globally unique | email becomes the login; see Auth |

## Serial numbers must be rebuilt, not just scoped

Current generation counts every row created that day:

```python
existing_count = Patient.objects.filter(created_at__date=date).count()
```

Three separate problems under multi-tenancy:

1. **Cross-tenant business-metrics leak.** The count spans all tenants, so Tenant B's ticket numbers silently disclose Tenant A's daily patient volume to a competitor.
2. **Still race-prone.** The `transaction.atomic()` + `select_for_update()` fix from BE-003 is currently a *no-op* — SQLite ignores `SELECT … FOR UPDATE`. It only becomes real once we are on PostgreSQL (Step 0).
3. **O(n) on every insert.** A full table count runs each time a record is created, and gets permanently slower as the clinic grows.

Replace with a counter row locked per tenant:

```python
class SerialCounter(models.Model):        # (tenant, scope, date) → last_value
    tenant, scope, date, last_value
    class Meta:
        constraints = [UniqueConstraint(fields=['tenant', 'scope', 'date'], …)]
```

`select_for_update()` on that single row is genuinely atomic on PostgreSQL, tenant-private, and O(1).

## Authentication changes

- `User.tenant` FK — nullable **only** for platform staff.
- `USERNAME_FIELD = 'email'`, email globally unique; `username` drops its global unique constraint.
- An explicit `is_platform_staff` flag for SaaS operators who legitimately span tenants. They bypass tenant scoping through one named, audited code path — never implicitly, and support impersonation stays time-boxed and logged per doc §64.
- `accounts/apps.py` currently seeds `Admin`/`Reception` roles via `post_migrate`. That becomes **per-tenant provisioning** at tenant-creation time; otherwise every new deployment creates orphan global roles belonging to no tenant.

## Migration sequence — and where to start

Each step ships independently and is reversible. **Steps 0–5 are invisible to the current clinic**: the system keeps behaving exactly as it does today, with exactly one tenant. That is what makes this safe to do on a live system holding real patient records — the risky "second tenant" moment does not arrive until Step 7, by which point isolation is enforced at four layers and covered by tests.

| Step | Work | Why here |
|---|---|---|
| **0** | **PostgreSQL + managed hosting.** App stays single-tenant and behaviourally identical; verify with the existing 23 tests. | RLS is PostgreSQL-only, and moving data is far cheaper *before* schema churn. Also makes the BE-003 locking fix real. |
| **1** | `tenants` app + `Tenant` model; create Tenant #1 = the current clinic. | Nothing references it yet — zero risk. |
| **2** | `tenant` FK on all 16 models + data migration backfilling every row to Tenant #1. | Biggest schema change; still one tenant, so behaviour is unchanged. |
| **3** | Per-tenant unique constraints + `SerialCounter` rewrite. | Safe only once every row has a tenant. |
| **4** | Enforcement: contextvar + middleware, `TenantManager`, RLS policies, cross-tenant test suite. | Isolation becomes provable while there is still only one tenant to break. |
| **5** | Auth rework: email login, `User.tenant`, platform-staff flag, per-tenant role seeding. | Depends on tenant existing; last of the invisible steps. |
| **6** | Public identifiers — UUID/slug replacing `<int:pk>` everywhere (doc §49/§50). | Do it before the URL surface grows; touches every view and template. |
| **7** | Tenant onboarding and provisioning; **first second tenant**. | The first real proof the isolation works. |

Only after Step 7 does the SaaS business layer make sense: plans, subscriptions, entitlements and feature flags, SaaS admin portal, billing (doc §10/§11/§22/§84).

**Start with Step 0 — PostgreSQL and the hosting move — then Steps 1 and 2.** Step 0 is a prerequisite for the isolation model rather than a preference, and doing it first means the large `tenant` backfill migration runs exactly once, on the database we intend to keep.

## Non-goals and risks

- **Don't rename `Branch` → `Clinic`.** Churn across 40+ files, no functional gain.
- **Don't accept tenant identity from the client.** Session-derived only.
- **Don't grant the app's DB role `BYPASSRLS`** — it silently disables Layer 1 entirely.
- **Don't build billing or the SaaS admin portal before Step 7.** Selling seats on unproven isolation is the one genuinely unrecoverable mistake available here.
- **Blockchain and AI (doc §48/§52) stay out of scope** until the core platform is real and has paying tenants.
- `dummy_data.py` and the `reports/` recipient list both assume a single tenant and need revisiting during Steps 2–3.
