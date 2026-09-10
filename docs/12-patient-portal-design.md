# 12 — Patient Portal: architecture and design

Status: **design for review**. Nothing in this document is implemented yet.

The requirement, as stated from the start:

> The patient must only ever access their own data, even if they know another
> patient's UUID. The API must enforce authorization server-side; React UI
> hiding is never a security boundary.

Everything below is organised around that sentence. The portal is the first
part of the system whose users are **not staff**, and it is the part most
likely to be probed, because every patient is an authenticated user with a
reason to be curious.

---

## 1. The one design decision everything else follows from

**A patient is not a `User`.**

The tempting shortcut is to give patients a `User` row with a `tenant` and a
"Patient" role. It would be a disaster, for a structural reason:

* `TenantMiddleware` binds the tenant from `request.user.tenant`.
* `IsClinicMember` admits any authenticated user who has a tenant.

A patient `User` would therefore pass the clinic API's outermost gate and be
one forgotten role check away from `/api/patients/` — the whole clinic's patient
list. Every staff endpoint would have to remember to exclude patients, forever.
That is the "fails open" direction this codebase has refused everywhere else.

Instead:

| | Staff | Patient |
|---|---|---|
| Identity | `accounts.User` | new `portal.PatientAccount`, 1:1 with `patients.Patient` |
| Session | Django session cookie | separate `portal_session` cookie, path `/api/portal/` |
| Tenant binding | `TenantMiddleware`, from `request.user` | explicit `tenant_context(account.tenant)` in the portal base view |
| API | `/api/*` | `/api/portal/*` only |

The two never meet. A patient session cannot authenticate against a staff
endpoint because it is not a Django session at all, and a staff session is
ignored by the portal because the portal reads only its own cookie.

## 2. Authentication

### Phase 1 — no SMS provider needed (recommended to ship first)

1. At the front desk, staff press **«دعوة للبوابة»** on the patient's file.
2. The server creates a single-use invitation: a random 32-byte token, stored
   **hashed** (like a password reset token), valid 72 hours, bound to one
   patient.
3. Staff hand the link over — printed on the receipt as a QR code, or sent by
   the clinic's own WhatsApp.
4. The patient opens it and sets a password. The token is consumed.
5. Afterwards: log in with **phone number + password**, scoped to the clinic's
   portal URL (`/portal/<clinic-slug>/`).

This works on day one on cPanel with no third-party account, which is why it
is Phase 1.

### Phase 2 — OTP by SMS or WhatsApp

Replaces the password with a one-time code. Needs a provider and credentials
(decision D1 below). The account model does not change; only the login step.

### Controls in both phases

* Login throttled per phone **and** per IP; lockout after repeated failures.
* One message for "no such account" and "wrong password" — the same rule the
  staff login follows.
* Portal session: server-side `PortalSession` row, token stored hashed,
  `HttpOnly`, `Secure`, `SameSite=Lax`, idle timeout 30 minutes, absolute
  lifetime 7 days, revocable by staff ("sign this patient out everywhere").
* Changing a phone number on the patient record revokes their portal sessions.

## 3. Authorization — how "only their own data" is made true

Three layers, each sufficient on its own:

1. **Tenant.** The portal base view enters `tenant_context(account.tenant)` for
   the request, so row-level security binds exactly as it does for staff. A
   bug in layers 2–3 still cannot reach another clinic.
2. **Patient, at the queryset.** Every portal view builds its queryset from
   `Model.objects.filter(patient=request.portal_patient)` — never from a
   generic queryset filtered afterwards, and never with the patient taken from
   the URL. There is **no patient identifier in any portal URL**: `/api/portal/
   appointments/`, not `/api/portal/patients/<uuid>/appointments/`. The
   question "whose data" is answered only by the session.
3. **Release.** Clinical items are visible only once the clinic releases them
   (section 4).

A record UUID in a portal URL (`/api/portal/prescriptions/<uuid>/`) is looked
up **inside** the patient-filtered queryset, so another patient's UUID is a 404
indistinguishable from one that never existed — the same property the staff
API already tests.

**The tests that must exist before this ships**, modelled on
`api/tests/test_isolation.py`:

* Patient A fetching each of patient B's records by UUID → 404, same body as a
  random UUID.
* Patient A cannot see B's records through any list, filter, or search.
* A patient session is refused by every staff endpoint; a staff session is
  refused by every portal endpoint.
* A patient of clinic X, with X's cookie, gets nothing from clinic Y's portal.
* Unreleased results never appear, in lists or by UUID.

## 4. What a patient sees

Conservative by default. Everything beyond the first column is a clinic
setting, off until the clinic turns it on.

| Always | Only when released by a doctor | Never |
|---|---|---|
| Their appointments (past and upcoming) | Lab results (`released_to_patient`) | Examination notes |
| Their prescriptions, printable | Attachments (`released_to_patient`) | Other patients, obviously |
| Their payments and receipts | Diagnosis text (clinic setting, D2) | Staff names beyond the treating doctor |
| Their treatment plan progress (sessions done / planned) | | Internal notes |
| Their recorded allergies | | Audit data |

"Released" is a new boolean plus `released_at` / `released_by` on `LabResult`
and `MedicalAttachment`. A result is not the patient's to read the moment it
is typed — a doctor may need to call them first. Critical results in particular
should never reach a patient before a clinician has.

## 5. What a patient can do

Phase 1:

* Update their contact phone/email (re-verified) and set a password.
* **Request** an appointment: creates an `Appointment` with a new status
  `requested`, which reception confirms or declines. The portal never books
  directly into a doctor's schedule (D3).
* Download their prescription and receipt as PDF.

Later, each blocked on a decision:

* Online payment — needs a gateway (P4 in `06-implementation-progress.md`).
* Reminders by WhatsApp/SMS — needs the provider from D1.

## 6. Audit

Every portal read of a clinical item writes an `AuditLog` entry against the
clinic ("patient viewed lab result 20260910-003"). Staff can see in the
patient's file what the patient has opened — useful when a patient calls about
a result.

## 7. Where it lives

* Backend: new Django app `portal/` — models (`PatientAccount`,
  `PortalInvitation`, `PortalSession`), authentication, views under
  `/api/portal/`. It imports from the clinical apps; they never import from it.
* Frontend: a third section of the React app at `/app/portal/<slug>/`, with its
  own shell — mobile-first, because this is the one audience that will use it
  almost entirely on a phone.
* Staff side: «دعوة للبوابة» and «إصدار للمريض» buttons on the patient file and
  on lab results / attachments.

## 8. Decisions needed before building

| # | Decision | Recommendation |
|---|---|---|
| D1 | SMS/WhatsApp provider for OTP and reminders | Ship Phase 1 (invite + password) without one; pick a provider for Phase 2 |
| D2 | May patients read the diagnosis text? | Off by default; per-clinic setting |
| D3 | Direct booking or request-and-confirm? | Request-and-confirm |
| D4 | Guardians for minors / family accounts | Out of scope for v1; one account per patient |
| D5 | Portal URL: path per clinic (`/portal/<slug>/`) or subdomain | Path — works on cPanel without wildcard DNS or certificates |

## 9. Estimate

With the recommendations above: models and auth, portal API with the isolation
test suite, release flags on two models, the staff buttons, and the mobile
portal screens. The isolation tests are the part not to shorten.
