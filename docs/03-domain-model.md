# 03 — Domain Model (current state)

ER-style map of what's actually implemented, with FK cardinality and where branch-scoping is/isn't enforced at the view layer (✅ enforced in list+detail+update+delete, ⚠️ enforced in list only, ❌ not enforced anywhere).

```
Branch  ⚠️ (branch mgmt itself has NO auth check — see audit C5)
 ├── User (accounts)            FK branch, nullable          ⚠️
 │     └── role → ClinicRole    FK role, nullable (flat, not branch-scoped)
 ├── Employee                   FK branch, required           ⚠️
 │     ├── employee_type → EmployeeType
 │     ├── salary_type → SalaryType
 │     └── specializations → Specialization (M2M)
 ├── Patient                    FK branch, nullable           ⚠️ (list ✅, detail/update/delete ❌ — C4)
 │     └── Appointment          FK patient, required          ⚠️ (list ✅, detail/update/delete ❌ — C4)
 │           ├── doctor → Employee (limit_choices_to employee_type__name="Doctor")
 │           ├── specialization → employees.Specialization
 │           ├── service → services.Service
 │           ├── branch  FK branch, nullable
 │           └── created_by → accounts.User
 │                 └── Payment  FK appointment, required       ⚠️ (list ✅, detail/update/delete ❌ — C4)
 │                       ├── patient → patients.Patient (redundant with appointment.patient)
 │                       ├── method → PaymentMethod
 │                       └── branch FK branch, nullable
 └── Expense                    FK branch, required            ⚠️ (list ✅, update/delete ❌)
       ├── category → ExpenseCategory
       └── employee → employees.Employee (nullable)

Service                          global, not branch-scoped
 └── specialization → employees.Specialization

Notification                     FK user (correctly scoped — see the good pattern in audit doc)
AuditLog                         FK user, generic model_name/object_id (no branch column at all — H2)
ReportRecipient (reports)        email list for scheduled report delivery
```

## Key structural gaps vs. doc/readme.md's domain vision (§7)

| doc/readme.md concept | Current reality |
|---|---|
| `Tenant` / `SaaS` / `Organization` | **Does not exist.** `Branch` is the only scoping unit, and it's flat (no parent organization). |
| `Clinic` | Closest match is `Branch`, but `Branch` is a physical location, not a legal/billing entity — no contracts, no plan, no subscription tied to it. |
| `Doctor` (multi-clinic) | `Employee.branch` is a single required FK — a doctor cannot belong to more than one branch today, contradicting doc §15/§16. |
| `Pricing Engine` / `Contracts` / `Commission` | `Service.base_price` is a single flat `Decimal`. No contract model, no commission model, no per-branch/per-doctor override, no historical snapshot of price-at-time-of-transaction (`Appointment.price` is stored per-appointment, which is the right instinct, but nothing populates/derives it from a pricing engine — it's a plain form field today). |
| `Invoices` | Doesn't exist — `Payment` is a flat receipt record, no line items, no invoice numbering separate from `receipt_number`, no partial-payment/remaining-balance tracking. |
| `Financial Ledger` | Doesn't exist — `financial_report` computes aggregates live from `Payment`/`Expense` querysets on every request; there's no immutable ledger table. |
| `Medical Records` / `Prescriptions` / `Diagnosis` | **Doesn't exist at all.** `Patient.notes` is the only free-text field; there is no visit/diagnosis/prescription model anywhere in the 9 apps read. This is one of the largest gaps if the clinical side of doc/readme.md is a real priority. |
| `Queue` | `Appointment.status` has a `"waiting"` value and a `waiting_list` view exists ([appointments/views.py:123-143](../appointments/views.py#L123-L143)), but there's no queue position/estimated-wait-time/priority field — it's a filtered list, not a queue engine. |
| `Treatment Plans` / `Sessions` / `Packages` | Doesn't exist. |
| `Resources` (rooms/equipment) | Doesn't exist. |
| `Subscription` / plan entitlements | Doesn't exist — there's exactly one organization using this codebase today. |

## What maps cleanly (reuse as-is or extend, don't replace)

- `Branch` → could become `Clinic` under a new `Tenant` parent with minimal schema disruption (add one FK).
- `Employee` + `EmployeeType` + `Specialization` → solid basis for `Doctor`/`Staff`, needs M2M to branches instead of a single FK if multi-clinic doctors are wanted.
- `Appointment` → solid basis for the appointment engine; status enum needs expanding to match doc §20's lifecycle (pending/confirmed/checked-in/completed/cancelled/no-show/rescheduled) if that workflow granularity is wanted.
- `Payment`/`Expense`/`PaymentMethod`/`ExpenseCategory` → solid basis for billing; needs an `Invoice` layer on top and eventually a ledger if the financial architecture in doc §33-36 is pursued.
- `AuditLog` → solid basis for doc §65's audit log, needs a `branch`/tenant column and before/after diffs.
