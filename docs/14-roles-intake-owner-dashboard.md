# Roles, first-visit intake, and the group owner's dashboard

Implemented 2026-09-10 on the existing architecture: no new tenancy model,
RLS unchanged in kind (two new tables added to the same model-derived policy
set), the React SPA extended rather than replaced.

## 1. Roles

A **group** is a `Tenant`; a **clinic** is a `Branch`. The rule lives in one
place, [accounts/roles.py](../accounts/roles.py), and every view, serializer,
template and the session payload asks it.

| Role | Reach | Can |
|---|---|---|
| Platform admin | no tenant; `/app/platform` | read-only, audited, explicitly selected tenant (unchanged) |
| **Owner** (new) | every clinic of *their* group | everything in the group: clinics, plan, group settings, staff incl. other Owners, group dashboard |
| **Admin** (now clinic admin) | their own clinic | staff (Admin/Doctor/Reception) of their clinic, attendance, services, reference lists |
| Doctor | their clinic | clinical records, reported history |
| Reception | their clinic | registration, appointments, payments; may *enter* medical history, may not *read* it back |

* `scope_queryset_to_user()` is the single branch filter: Owner → all; anyone
  else → their branch; no branch → nothing.
* `accounts.0007_owner_role` promotes every existing Admin to Owner, so no
  existing account loses reach on upgrade. Reversible.
* A clinic Admin cannot create an Owner, cannot staff another clinic, cannot
  see or edit an Owner, and cannot promote themselves through the old
  settings form (that form used to accept a posted role — fixed).
* The old server-rendered financial report double counted when a branch had
  both payments and expenses (two reverse joins in one `annotate`); it now
  uses subqueries, and a clinic Admin sees only their clinic there too.

## 2. First-visit intake

One service, [patients/intake.py](../patients/intake.py), used by both doors:
the front desk (`POST /api/intake/register/`) and the patient portal
(`POST /api/portal/<slug>/register/`, off unless the group turns it on).

Structured data, not a JSON blob:

* `Patient` — contact, governorate/area, emergency contact, **referral source**
  (coded) with the referring doctor's name / referrer, the patient who
  recommended them, the **recommended doctor** (kept apart from the doctor
  they want to see), consent timestamp and contact preferences.
* `PatientMedicalProfile` (1:1) — smoking, medications, surgeries,
  hospitalisations, family history, "conditions reviewed".
* `PatientCondition` — one row per chronic condition (coded, or "other" with
  a name), with details and current treatment.
* `Allergy` — the existing model; the intake writes into it.
* `PatientIntake` — each visit's reason in the patient's words: case type,
  symptoms, onset, specialty, requested doctor, a diagnosis *reported by the
  patient*. The physician's diagnosis stays on the visit.

Controls: consent is required; a requested doctor must be a Doctor, of the
chosen specialty, at the chosen clinic; Reception registers only into their
own clinic; a phone/national-ID match returns 409 with the matches the caller
may see and only a *count* for other clinics (override with `confirm_new`);
the plan's patient limit applies. Portal submissions are quarantined
(`needs_review`), never reveal whether the person already exists, need CSRF,
are throttled (10/hour), and do not use up the plan until confirmed. The desk
confirms, merges into the existing patient, or rejects them.

Screens: a six-step wizard (`/app/patients/new`, and
`/app/portal/<slug>/register`), a review queue (`/app/patients/review`), and
a "reported history" card on the patient file for clinical roles.

## 3. The owner dashboard

`GET /api/owner/overview/?from=&to=&branch=` (Owner only) and `/app/owner`.

Revenue, expenses, net; billed / collected / outstanding; revenue by clinic,
doctor, specialty; daily series; expenses by category; appointments by status
(including the new `completed` / `cancelled` / `no_show`), today and the next
7 days; new, returning and pending patients; referral sources; case types;
doctors' workload and attendance; a per-clinic comparison table with quick
links that carry `?branch=` into the patients, appointments and payments
screens. The clinic switcher ("All clinics / Clinic A / …") and the date
range live in the URL.

Each table is aggregated by its own grouped query — never two reverse joins
in one aggregate — and an unknown or foreign `branch` is a 404.

## 4. Attendance

`Attendance` (one row per employee per day: present / late / absent / leave,
times, minutes late). `/api/attendance/sheet/` reads and saves a day's sheet
in one transaction; `/app/attendance` for Owner and clinic Admin.

## 5. Languages

`frontend/src/i18n/` — Arabic (default) and English dictionaries, `t()`,
`<html lang dir>` switched with the language. Choice lists come from the
server as codes (`GET /api/meta/choices/`) and are translated client-side, so
no screen keeps its own copy of a list. `api/tests/test_translations.py`
fails when a code, or a key used in a screen, is missing from either
language, or when the two dictionaries drift.

The app shell (navigation, header) and every screen added here are
translated. **Screens built earlier are still Arabic-only**: they render
correctly in the English layout (LTR), but their own words are Arabic until
they are moved onto `t()`.

## 6. Migrations

`accounts.0007_owner_role`, `appointments.0007`, `billing.0006` (indexes),
`employees.0007_attendance`, `medical.0009`, `patients.0007`,
`tenants.0014_rls_intake_attendance` (RLS on the new tables),
`tenants.0015_tenant_portal_self_registration`.
