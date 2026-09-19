# 15 — Public clinic portal and online booking: plan and progress

Started 2026-09-19. This file is the source of truth for the work: what was
decided, what each phase changes, and what is finished. Backend and frontend
are tracked separately in every phase, and a part is only marked `DONE` when its
own tests / build passed (date and what was run are written next to it).

Legend: `[ ]` not started · `[~]` in progress · `[x]` done and verified · `[-]` deferred on purpose.

Working rules (from the brief): analyse → plan → implement → test → review; no
rewrite of what works; no deleting migrations or data; incremental; reuse the
portal that already exists (`portal/`, `frontend/src/features/portal/`); a green
frontend proves nothing about security — the API enforces everything.

---

## 1. Decisions (settled with the user)

| # | Decision |
|---|---|
| D1 | Vocabulary: `Tenant` = the group ("المجمع"); `Branch` = the clinic; Admin = clinic manager; Owner = group owner. |
| D2 | The public page is at group level (`/app/portal/<slug>`), with one section per clinic (branch). |
| D3 | A booking from the portal is a **request** (`requested`) by default: the clinic phones the customer and fixes the real date and time. A per-clinic setting allows instant confirmation. |
| D4 | A `requested` booking does **not** hold a slot (customers ask for a *preferred* time; the clinic resolves it by phone). Locking and overlap checks apply to instant-confirm clinics and to reception's confirmation. |
| D5 | Linking a new account to an existing patient needs proof of ownership: an OTP to the e-mail on the patient's file (default channel now). SMS is a second channel, plugged in when a provider is enabled. A patient with no e-mail on file goes through the existing reception review. Matching by phone alone is refused. |
| D6 | Offers ("العروض") come after Phase 5. |
| D7 | Doctor schedule: weekly, per doctor per branch, one break per day. |
| D8 | Public images: the Owner uploads the group's logo/cover and any branch's; a branch Admin may upload for their branch, but it stays **pending** and is public only after the Owner approves. The public logo/cover are separate from the print letterhead logo (`Branch.logo`), which is unchanged. |
| D9 | `Service` (group) → `BranchService` (is it offered / bookable online in this clinic) → `DoctorServiceRate` (who, at what price). A clinic offers a service only if `BranchService` is active **and** a doctor of that clinic has an active rate with a valid price. |
| D10 | A patient of branch A may book at branch B only if the group enables `portal_allow_other_branches` (default off). Branch B's staff then see the patient with limited, read-only fields, only while the booking there is confirmed and not cancelled. |
| D11 | Online booking needs a doctor in v1; device/room/non-doctor resources are a later phase. |
| D13 | Online payments are recorded inside a shift before they count as paid: one system-opened online shift per clinic (Phase 8). |
| D14 | Things sold by quantity: the Owner or an Admin marks a service as sold by quantity (pulses, ml, units); its price is then per unit and a booking's total is unit price × quantity. Others stay one thing. |
| D12 | Complex pricing (per pulse / area / package / ml) is a separate phase after the Service → Branch → Doctor architecture is stable. |

Customer journey:

```
Public page → Service → Available clinics → Doctor → Date → Preferred time
 → Login / Register (OTP-verified) → Request sent (requested) → clinic calls
 → confirmed (waiting) → Payment (pay at clinic by default; online where enabled)
```

Existing pieces reused as they are: `PatientAccount` / `PortalSession` / OTP
(`portal/`), `register_patient` quarantine flow, `DoctorServiceRate` +
`billing.pricing`, `Appointment` statuses, `Payment` separate from the
appointment, gateways in `platform_admin/clinic_pay.py`, `notifications.maillog`.

---

## 2. Baseline (Phase 0.5)

The working tree carries unrelated work from another session (e-mail log,
`project/config.py`). Not touched by this plan.

- [x] Settings load and `makemigrations --check` clean, using the environment
      override documented in `project/config.py`:
      `DJANGO_ENV=development DJANGO_DB=sqlite` (the file itself is set to
      production + PostgreSQL and has no `POSTGRES_URL` in `.env`, so a plain
      `manage.py test` cannot start).
- [ ] Full-suite baseline number. A full run takes many minutes; it was stopped
      on request. Phases are verified with the tests they touch plus the
      isolation suites (`portal`, `api.tests.test_isolation`,
      `api.tests.test_branch_about`, …). Record the full-suite result here when run.

---

## 3. Phase 1 — Public clinic page

Goal: an unauthenticated visitor at `/app/portal/<slug>` sees the group, its
clinics, contact details, hours, the doctors who agreed to be shown, and the
approved logo/cover — and can go to sign in or register.

### 3.1 Backend  — status: `DONE` (2026-09-19)

Verified: `api.tests.test_public_page` (23 new) + `api.tests.test_branch_about` = 45 tests OK;
neighbouring suites `test_serializer_contract`, `test_relations`, `test_isolation`, `portal` = 69 tests OK;
`makemigrations --check` clean (run with `DJANGO_ENV=development DJANGO_DB=sqlite`).

- [x] `Employee.show_publicly` (bool, default False) + migration; editable in
      `EmployeeSerializer` (Admin/Owner only; a doctor cannot publish themselves).
- [x] Public media fields, with approval (D8):
      - `Tenant`: `public_logo`, `public_cover` (Owner only, live immediately).
      - `Branch`: `public_logo`, `public_cover` (approved) and
        `pending_public_logo`, `pending_public_cover`, `media_status`
        (`""` nothing waiting / `pending` / `rejected`; approved = moved to `public_*`), `media_review_note`,
        `media_reviewed_by/at`.
      - image validation: JPEG/PNG/WebP, size cap, verified as a real image,
        random file names; only the approved file is ever returned publicly.
- [x] Endpoints (staff, `IsClinicAdmin`): upload/replace/remove media; Owner
      approve/reject a pending branch image; list what awaits approval.
- [x] `PublicAboutView` extended (existing keys unchanged): group logo/cover,
      per-branch approved logo/cover, social links (`print_links`), and doctors
      with `show_publicly=True` and an active account — name, specialties,
      approved `public_profile` tagline/links only. Never e-mail, phone,
      national id, salary, or any identifier of the employee record (no uuid is returned).
- [x] Migration checked; RLS unaffected (columns on existing tables).
- [x] Tests: unpublished / stopped doctor absent; no internal fields leak; hidden
      branch absent; pending image never public; Admin cannot approve; Admin of
      branch A cannot upload for branch B; tenant isolation intact.

### 3.2 Frontend  — status: `DONE` in source; `dist` not rebuilt (2026-09-19)

Verified: `vite build` succeeds (built to a scratch folder). **Not verified in a
browser** — no visual/click-through check has been done; do that before release.
`frontend/dist` (committed for cPanel) is intentionally left as is: it holds another
session's uncommitted build. Run `npm run build` in `frontend/` when releasing.

- [x] Public landing page (`/portal/<slug>` when not signed in) instead of the
      redirect to sign-in; reuses `PortalAbout`; hero with approved logo/cover;
      one section per clinic; doctors; contact; buttons: sign in / register.
      (The "Book" button arrives with Phases 3–5.)
- [x] `portalApi`: the existing `about` call now carries everything; strings are written in Arabic in the components (like the rest of the portal), so the shared i18n files were not touched.
- [x] Staff: "Show on public page" checkbox on the employee form.
- [x] Staff: `/about/media` (linked from the About screen): Owner sets group + any clinic and approves/rejects; Admin uploads for their clinic and sees "awaiting approval" / the rejection note.
- [x] `vite build` succeeds. `frontend/dist` NOT rebuilt (see above) — do it at release.

---

## 4. Phase 2 — Customer identity

### 4.1 Backend — `DONE` (2026-09-19)

Verified: `portal.test_account` (29 new) + all of `portal`, `api.tests.test_translations`,
`api.tests.test_owner_email` = 124 tests OK; `makemigrations --check` clean.

- [x] OTP channel abstraction (`portal/otp_channels.py`): `EmailChannel` is the only
      one registered; SMS = register a second channel when a provider exists. Used by
      the new signup and e-mail-change flows. (The existing login-by-code still calls
      `portal.mail` directly because it groups households on one address; move it onto
      the channel when SMS is added.)
- [x] `PortalVerification` (tenant-owned, RLS via `tenants.0022`, migration
      `portal.0003`): hashed code + hashed ticket, 10 minutes, 5 guesses, once.
- [x] `POST account/start/` + `POST account/verify/` (public, CSRF, throttled per
      client and per address, behind `Tenant.portal_self_registration`): a patient is
      linked only if exactly one confirmed patient has the same phone **and** name and
      an e-mail on file, and the code goes to *that* e-mail, not the typed one;
      otherwise a new quarantined patient (`needs_review`) is created after the typed
      address is proved. Same answer either way (no oracle). Linking sets the password
      and ends the account's old sessions.
- [x] Merge keeps the account: `patients.intake.merge_registration` moves a signup's
      `PatientAccount` onto the file it duplicates (deleting the source would have
      cascaded it away).
- [x] `GET/PATCH me/profile/` (address, area, whatsapp, emergency contact, contact
      preferences only — never name, phone, clinic or anything clinical) and
      `POST me/email/` + `me/email/verify/` (new address proved before it replaces the
      old; tickets are looked up inside the patient's own rows). Phone changes stay with
      the clinic (no SMS to prove a new number; docs/12).
- [x] E-mail log kinds added; the log stores the message masked, never the code.

### 4.2 Frontend — `DONE` in source (2026-09-19)

Verified: `vite build` succeeds. Not browser-tested; `dist` not rebuilt.

- [x] `/portal/<slug>/signup`: form then code, wording that never reveals whether the
      person is already a patient; linked from the landing and sign-in pages.
- [x] "حسابي" tab: contact details, preferences, e-mail change with code.
- [ ] Wiring signup *inside* the booking journey (choose service → clinic → … → sign
      up) comes with the booking wizard (Phase 5).

---

## 5. Phase 3 — Service → Branch → Doctor catalogue

### 5.1 Backend — `DONE` (2026-09-19)

Verified: `api.tests.test_catalogue` (37 new) with `test_public_page`, `test_serializer_contract`,
`test_search_and_offerings`, `tenants.test_rls` = 86 tests OK (14 skipped: `test_rls` needs
PostgreSQL — **the RLS policies for the new tables are therefore not exercised here; run
`tenants.test_rls` against PostgreSQL before release**); related `test_contracts`,
`test_booking_payment` OK; `makemigrations --check` clean.

- [x] `services.BranchService` (unique `(tenant, branch, service)`; migrations
      `services.0007`, RLS `tenants.0023`) and `Service.duration_minutes` /
      `Service.price_display` (fixed / starting from / after evaluation — no advanced
      pricing, D12).
- [x] **Backfill** `services.0008`: each active doctor contract switches its service on in
      every clinic the doctor works in (home + visiting). Reads each group under its own
      database binding (works under PostgreSQL RLS). Idempotent; tested through the
      historical app registry.
- [x] `services/catalog.py`: `offerings()` / `resolve_offering()` — the one rule for
      "bookable" (clinic running and shown · service active · `BranchService` active and
      online-bookable · doctor is a Doctor, `show_publicly`, login not stopped, works in
      the clinic · active contract line with a valid price, unless priced after
      evaluation). A contract alone never makes a clinic offer a service, and a switch
      alone never puts an unqualified doctor in front of a customer. Constant query
      count (a test caught an N+1 in price lookup; fixed with `billing.pricing.price_from_rate`).
- [x] Public, read-only endpoints `portal/<slug>/catalog/services/`, `…/<service>/branches/`,
      `…/<service>/branches/<branch>/doctors/` (nothing internal returned; other groups'
      uuids are 404).
- [x] Staff `GET/PUT /api/branch-services/` (Owner: any clinic; Admin: own; reception 403)
      with "doctors ready" per service; service serializer exposes duration / price display.
- Note: the existing signed-in `booking/options/` request flow is untouched until Phase 5,
  so nothing that works today changed.

### 5.2 Frontend — `DONE` in source (2026-09-19)

Verified: `vite build` succeeds. Not browser-tested; `dist` not rebuilt.

- [x] Public `/portal/<slug>/services` → `…/services/<service>` (only the clinics that offer
      it) → `…/<service>/<branch>` (its doctors and prices); "الخدمات والأسعار" button on the
      landing page. Prices read "يبدأ من …" / "بعد تقييم الطبيب" per service.
- [x] Staff `/services/branches` (linked from Services): per clinic, switch a service on and
      whether it takes online bookings, with the doctors-ready count; Services form gains
      duration and price description.

---

## 6. Phase 4 — Availability

### 6.1 Backend — `DONE` (2026-09-19)

Verified: `api.tests.test_availability` (43 new) OK; `makemigrations --check` clean. RLS for the
three new tables (`tenants.0024`) is not exercised on SQLite — run `tenants.test_rls` on PostgreSQL.

- [x] `appointments.DoctorSchedule` (per doctor · clinic · weekday, one break; DB check
      constraints: ends after start, break inside the hours and both-or-neither),
      `DoctorTimeOff`, `BranchHoliday` (a clinic, or the whole group when no clinic). Migration
      `appointments.0009`, RLS `tenants.0024`.
- [x] `appointments/availability.py`: hours cut into service-length steps around the break, minus
      time off, holidays, and bookings that occupy the doctor **at any clinic** (waiting, called,
      entered, quick, completed — a `requested`, cancelled or missed one holds nothing, D4);
      nothing sooner than 60 minutes, nothing past 60 days. `available_slots`, `available_days`,
      `is_offered` (what booking will re-check). Constant 4 queries whatever the range.
- [x] Public `catalog/availability/?service&branch&doctor&date` and `…/days/` (throttled; the
      choice is re-resolved by `resolve_offering`, so an unbookable one is a 404; only times are
      returned, never who booked them).
- [x] Staff `GET/PUT /api/schedules/` (a doctor's week at a clinic; Owner any clinic, Admin own),
      `/api/doctor-time-off/` (reason is internal, never public) and `/api/branch-holidays/` (a
      group-wide day is the Owner's; an Admin sees it but cannot change or remove it).

### 6.2 Frontend — `DONE` in source (2026-09-19)

Verified: `vite build` succeeds. Not browser-tested; `dist` not rebuilt.

- [x] Staff «مواعيد الأطباء» (week grid, Saturday first), «إجازات الأطباء», «إجازات العيادة»
      (sidebar entries + i18n keys).
- [x] Public slot picker at `…/services/<service>/<branch>/<doctor>`: days that still have a
      time, then the times of a day; a chosen time is described as a *preferred* time the clinic
      confirms by phone. (Turning it into a request is Phase 5.)

---

## 7. Phase 5a — Cross-branch patient (D10)  · Phase 5 — Booking

### 7.1 Backend — `DONE` (2026-09-19)

Verified: `portal.test_booking` (20 new), `api.tests.test_visiting_patient` (22 new) OK; the
broad regression over everything the scoping change touches (isolation, doctor scoping,
permissions, relations, clinical, intake, checkin, dashboard, patients, accounts, all of portal)
— see the progress log for the result. `makemigrations --check` clean.

**Phase 5a — the visiting patient (D10).** A patient of clinic A with a *confirmed* booking at
clinic B (not `requested` / `cancelled` / `no_show`) is reachable by B's staff, and only so:
- [x] `scope_queryset_to_user(..., visiting=False)` — **opt-in**, so every screen that did not
      ask (patient export, dashboard counts, coupons, intake print…) behaves exactly as before. It
      admits the visitor for the patient record itself and for things hung off the patient's
      clinic (allergies) only; everything with a clinic of its own (bookings, visits, payments,
      results) stays cut by that clinic, so A's history never reaches B. Opted in: patient list /
      detail, allergies, the reported-history read, and the `patient` field of booking, payment
      and clinical serializers (so B's doctor can treat and B's desk can rebook them).
- [x] Limited, read-only: B sees name, file number, sex, birth date, age, phone 1 and clinic
      (`VISITING_FIELDS`) — no notes, national id, address, e-mail, second phone, WhatsApp,
      emergency contact, referral or consent — flagged `visiting: true`. Any change, delete or
      portal invite of a visiting patient is 403; the reported history is read-only.
- [x] `PatientViewSet.timeline` was unfiltered by clinic (safe only while a patient's clinic was
      the staff's clinic): every collection is now cut to what was recorded at the caller's own
      clinic (the Owner sees all). A patient's home clinic no longer sees the other clinic's
      bookings there either.
- [x] Cancelling (or no-show) closes access again; a booking at a third clinic opens nothing at B.
- [x] `Tenant.portal_allow_other_branches` (default **off**; `tenants.0025`; Owner setting).

**Phase 5 — booking** (`portal/booking.py`, `POST portal/<slug>/appointments/` with a `branch`):
- [x] The choice is re-resolved with `resolve_offering`, the time must be one of the doctor's
      offered times, the contract price is used, and a patient books at another clinic only when
      the group allows it. Default = a `requested` booking that holds no time (D3/D4, the clinic
      phones); `Branch.online_booking_confirms_at_once` (`branches.0013`, editable by the clinic's
      Admin or the Owner) = a `waiting` booking created under `select_for_update` on the doctor
      with the time re-checked inside the lock; a taken time is a 409. The lock is a no-op on
      SQLite, so true concurrency is exercised only on PostgreSQL — the tests check the
      sequential outcome.
- [x] `Appointment.source` (portal / reception / admin / phone / whatsapp; `appointments.0010`,
      default reception) with a backfill (`0011`) marking existing website requests; staff can
      say phone / WhatsApp / admin but never claim "portal", and a website booking keeps its
      source. Filter `?source=`. The older free-time request still works when no `branch` is
      sent (kept until the wizard is the only way in).
- Deliberate: reception's own confirmation (`requested` → `waiting`) is **not** blocked by the
  availability rules — the desk may move the time they agreed by phone.
- Not built: `Appointment.duration` (a booking's length is its service's `duration_minutes`).

### 7.2 Frontend — `DONE` in source (2026-09-19)

Verified: `vite build` succeeds. Not browser-tested; `dist` not rebuilt.

- [x] Booking wizard = the catalogue path ending in the slot picker's «إرسال طلب الموعد»: a signed-in
      patient sends it; someone not signed in is sent to sign in / up with `?next=` and brought
      back to the same doctor and time (`safeNext` only accepts this clinic's own portal paths).
      The home «طلب موعد» button now opens the catalogue; the free-time modal is removed.
- [x] Staff: «المصدر» column and filter in Appointments, a source choice when booking (desk /
      phone / WhatsApp / admin), «تأكيد الحجز من الموقع فوراً» per clinic (About), and the Owner's
      «السماح للمريض بالحجز في عيادة غير عيادته» (Portal settings).

---

## 8. Phases 6–10

Verified so far: the broad regression (isolation, doctor scoping, permissions, relations, clinical,
intake, check-in, dashboard, patients, accounts, all of `portal`) = **312 tests OK** after the Phase 5a
scoping change; the tests of each phase below were run on their own.

### Phase 6 — Customer portal · Backend `DONE` · Frontend `DONE` in source (2026-09-19)
- [x] `portal/my_bookings.py`: booking details (price, paid, due, payments), cancel, ask to reschedule
      — always from the patient's own bookings (another patient's uuid is an identical 404).
      Rules: only `requested`/`waiting`/`quick`; an unconfirmed request can always be withdrawn, a
      confirmed one only `Branch.online_cancel_notice_hours` ahead (default 24, 0 = any time; set in
      About); a booking with money on it is not cancelled online (refunds are the clinic's); a
      reschedule request moves nothing, must be a time the doctor is offered, and is cleared when
      the clinic edits the time (`Appointment.reschedule_requested_for` / `reschedule_note`;
      migrations `branches.0014`, `appointments.0012`). Staff can dismiss it.
- [x] Portal cards: cancel / withdraw with confirmation, «طلب تغيير الموعد» (reopens the same doctor's
      times), the clinic's reason when not allowed. Profile and e-mail change came with Phase 2.
- Tests: `portal.test_my_bookings` (24 + the Phase 7/8 classes below).

### Phase 7 — Admin integration · Backend `DONE` · Frontend `DONE` in source
- [x] No separate booking admin: website bookings are ordinary `Appointment` rows in the clinic's
      own screens. Dashboard «طلبات من الموقع» count (`appointments.online_requests`, per clinic);
      Appointments list: source column and filter, request-to-move badge with «تجاهل», and
      **تأكيد / رفض** buttons on a `requested` row (the existing `set_status`); booking form records
      the source (desk / phone / WhatsApp / admin). Assigning a doctor, viewing the customer,
      payment status and marking paid are the existing screens.
- Tests: `ManagerFlowTests` (5).

### Phase 8 — Payment · Backend `DONE` · Frontend `DONE` in source
- [x] Payment stays its own record beside the booking (already true: `Payment.appointment`); the
      portal payload now carries `price`, `paid`, `payment_status` (free / unpaid / partial / paid)
      and `pay_at_clinic`, and the card says what it costs, what was paid, and that the rest is paid
      at the clinic on arrival — or online when the clinic has a gateway and the booking is
      confirmed (existing gateways, `can_pay_online`). Nothing new stored: "pay at clinic" is the
      default for every booking not paid online.
- **Decided by the group owner (2026-09-19) — D13:** an online payment counts as paid only once it is
  confirmed **and** recorded inside a shift. Implemented as **one online shift per clinic**
  (`CashShift.kind="online"`, no person; `billing.shifts.online_shift`; migration `billing.0011` with
  constraints: one open online shift per clinic, a person's shift must have its person). The first
  confirmed online payment of a clinic opens it; every later one lands in it; Admin / the Owner review
  and close it like any shift (it prints, has a per-method summary, lists the bookings paid in it), and
  the next payment opens a fresh one. Recording happens inside `clinic_pay.confirm`'s transaction
  *before* the checkout is marked confirmed: if it fails, no payment, no shift, the checkout stays
  pending, the patient still owes it, the callback answers **503** (the gateway retries; idempotent) and
  the returning browser is told "being processed" (`?payment=pending`). If the booking was paid another
  way in the meantime the online money is still recorded, with a note to return the difference.
  Test-environment payments are never recorded. Staff screen: the shift list labels it
  «الدفع الإلكتروني · تلقائية»; its `kind` can be filtered.
- Tests: `PaymentLineTests` (5) and `api.tests.test_online_shift` (see the progress log).

### Phase 9 — Notifications · Backend `DONE`
- [x] `notifications/booking.py`, through what exists (no new system): e-mail to the patient via
      `maillog.deliver` — request received, confirmed, cancelled or moved by the clinic, and a
      reminder the day before (`manage.py send_booking_reminders`, for cron; once per booking per
      day) — only for patients with an address who belong to the website or agreed to e-mail.
      In-app `Notification` for the clinic's own reception and Admin: new website request (who to
      phone), the patient cancelling, asking to move. Sent on commit; a mail failure never stops a
      booking. The generic "new appointment" notice is skipped for website bookings (they get the
      specific one). E-mail log kinds added.
- Not built: SMS / WhatsApp (no provider); patient in-app notices (e-mail only).
- Tests: `portal.test_notifications` (20).

### Phase 10 — Security & tests · `DONE` for what SQLite can show
- [x] `portal/test_public_surface.py` (13 tests): every public read works without sign-in and returns no private
      key (id, tenant, national id, salary, commission, e-mail, notes…) or private value; public
      reads accept no writes; a stopped group serves nothing; every staff endpoint added here refuses
      anonymous callers, patients' portal sessions and (the management-only ones) reception; a
      session of one group is worthless in another; every public write and every signed-in
      patient's write is refused without the CSRF token.
- **Not verifiable here — do before release:**
  1. `tenants.test_rls` on **PostgreSQL** (skipped on SQLite): the policies for `PortalVerification`,
     `BranchService`, `DoctorSchedule`, `DoctorTimeOff`, `BranchHoliday` (`tenants.0022–0024`).
  2. **Concurrency** of instant-confirm booking: the lock is `select_for_update` on the doctor's
     row, a no-op on SQLite. Two simultaneous requests for one time should be run against
     PostgreSQL.
  3. Click-through in a browser of every new screen (nothing here was browser-tested).
  4. `frontend/dist` rebuild (`npm run build`) and collectstatic; `/media/` served by the web server
     in production (public logo/cover).
  5. The full test suite (only targeted suites and the 312-test regression were run).
- After Phase 5: offers (D6), advanced pricing (D12), resources beyond doctors (D11) — not started.

---

## 8b. Sold by quantity (requested 2026-09-19) — D14

The group owner: some things sold (products, treatments) take a quantity, so the total is
quantity × the unit price, and others do not — decided by the Owner or an Admin per item.
The sellable item in this system is the `Service`, so the switch lives there. (Stock /
inventory of goods is **not** part of this — nothing counts how many are left.)

### Backend `DONE`
- [x] `Service.requires_quantity` (default off), `quantity_unit` ("نبضة", "مل", "وحدة"),
      `min_quantity` (default 1), `max_quantity` (optional); `services.0009`. Edited through the
      ordinary Service screen/API, which is already management-only; limits validated (min > 0,
      max ≥ min).
- [x] `Appointment.quantity` and `Appointment.unit_price` (`appointments.0013`): for a quantity
      service `price` is the total = the doctor's unit price (contract, else catalogue) × quantity;
      the unit price is kept with the booking so a later contract change never rewrites it. Reception
      can never type a price (existing rule) — management may, and otherwise gets the computed total;
      editing a booking without touching doctor / service / quantity keeps its figures; switching to a
      service without quantity drops it. Coupons, what is owed, payments and the doctor's share all
      follow the total unchanged. `billing.pricing.apply_quantity` / `quantity_problem`.
- [x] Staff booking form gets `requires_quantity`, unit and limits from the doctor's offerings; the
      public catalogue shows every price of such a service as per-unit; the website booking takes
      `quantity`, validates it, and prices it server-side (a patient cannot set a price); the older
      free-time request refuses a quantity service (it cannot ask how many).
- [x] **The doctor sets the real quantity inside the clinic (2026-09-19, follow-up).** A service sold by
      quantity can be marked «الطبيب يحدد الكمية» (`Service.doctor_sets_quantity`, `services.0010`).
      Its bookings — at the desk or on the website — may go with no quantity: they are booked at the
      smallest quantity as an **estimate** (`Appointment.quantity_is_estimate`, `appointments.0014`).
      While the patient is in the room the doctor of the booking (or management; not the desk) fixes the
      real quantity with `POST /api/appointments/<uuid>/set-quantity/`: the total becomes the booking's
      own unit price × that quantity (a later contract change does not touch it), a coupon's discount
      can never exceed it, the estimate flag clears, and the front desk gets an in-app notice with what
      is left to collect — or that more was paid than the service now comes to, so the difference is
      returned. Allowed only while the booking is `waiting` / `called` / `entered`, within the limits
      management set. The doctor's room card (dashboard) shows the service, the quantity and its limits
      with a «حدّد الكمية» button — **never a price or a paid amount** (a doctor sees no clinic money but
      their own share). What a doctor records in a procedure or treatment session for such a service is
      held to the same limits. Payment stays as it was: the patient pays the estimate to be let in, and
      the difference is collected (or returned) by the desk afterwards.
- Not covered: no stock; procedures/sessions are not added to the booking's total (the doctor's figure
  for billing is the booking's quantity).
- Tests: `api.tests.test_quantity` (13), `portal.test_quantity` (12), `api.tests.test_doctor_quantity` (17).

### Frontend `DONE` in source
- [x] Services screen: «تُباع بالكمية», unit, min, max, and a badge in the list. Booking form: a
      quantity field (only for such a service) with the unit and limits, and the price follows
      unit × quantity; the appointment list shows «الخدمة × الكمية». Public catalogue: "لكل نبضة";
      the slot picker asks for the quantity and shows the total; the patient's card shows it.

---

## 8c. The public directory — the site's front door (requested 2026-09-19) — §10

The user asked where the "store" of clinics is: the public page existed per group
(`/app/portal/<slug>`) but nothing listed the groups. Decision: a public directory,
**opt-in per group** (`Tenant.listed_in_directory`, default off, Owner's switch), at
the bare domain. **`/` itself is the directory — served in place, no redirect and no
`/app`** (user, 2026-09-19: the store is the system's main domain). Django serves the SPA
shell at `/` (`project/urls.py`); `main.jsx` renders the router-free `DirectoryPage` when the
path is exactly `/`, and its links reach the app under `/app` with a full page load. Staff
sign in from the link in its header; stale bookmarks (`/patients/…`) still land in `/app/`
(`dashboard/test_entry.py`). In dev, a Vite middleware answers `/` with the same shell.

### Backend `DONE`
- [x] `Tenant.listed_in_directory` (`tenants.0026`, additive).
- [x] `api/directory.py` — `GET /api/directory/?q=`: public, throttled (`directory`, 60/min), cached one minute; each listed **running** group is read in its own tenant context (never one sweep across groups).
- [x] A card carries only what the public page already shows: approved logo/cover, running public clinics (name + address), specialties minus hidden, bookable services with the lowest price. No phone, e-mail, doctors, patients, staff (a test walks the response for secrets).
- [x] Search: every word must appear in the group name, a clinic, an address, a specialty or a service.
- [x] `PATCH /api/clinic-settings/` takes `listed_in_directory` (Owner only, real boolean) and clears the cache; the payload also returns `directory_url`.
- [x] Tests: `api/tests/test_directory.py` (19).

### Frontend `DONE` in source
- [x] `features/directory/DirectoryPage.jsx` + `directory.css` at the bare domain: search box, one card per group linking to its public page and its services; empty and error states; links to staff login and to "open your clinic".
- [x] Owner switch and copyable directory link in Settings › Patient portal.
- [ ] Not browser-tested; `dist` not rebuilt.

---

## 9. Progress log

| Date | Part | Result |
|---|---|---|
| 2026-09-19 | Public directory (§8c) | `tenants.0026`; `api/directory.py`; bare-domain page (`main.jsx` + `spa_index` at `/`); Owner switch; 19 tests OK; `vite build` OK (scratch dir) |
| 2026-09-19 | Plan written; baseline checked (settings + migrations) | see §2 |
| 2026-09-19 | Phase 1 backend | DONE — 3 additive migrations (`branches.0012`, `employees.0011`, `tenants.0021`), `branches/media.py`, `api/views/public_media.py`, `PublicAboutView` extended; 45 + 69 tests OK |
| 2026-09-19 | Online shift (D13) | `billing.0011`; 19 tests OK; money/shift regression 147 OK |
| 2026-09-19 | Quantity (D14) | `services.0009`, `appointments.0013`; 20 tests OK |
| 2026-09-19 | Doctor sets the quantity | `services.0010`, `appointments.0014`; 42 quantity tests OK; full run before it: 1066 OK (14 skipped, need PostgreSQL) |
| 2026-09-19 | Phases 6–10 | see §8 |
| 2026-09-19 | Phase 5a+5 backend | DONE — visiting-patient scope (opt-in), limited read-only view, timeline cut per clinic, catalogue booking (request / instant-confirm with lock), `Appointment.source`; 42 new tests OK; broad regression 312 tests OK |
| 2026-09-19 | Phase 5 frontend | DONE in source — request from the slot picker with `next` return, source column/filter, settings; build OK; not browser-tested |
| 2026-09-19 | Phase 4 backend | DONE — schedules/time off/holidays + RLS migration, availability engine, public endpoints, staff API; 43 tests OK |
| 2026-09-19 | Phase 4 frontend | DONE in source — schedule/time-off/holiday screens, slot picker; build OK; not browser-tested |
| 2026-09-19 | Phase 3 backend | DONE — `BranchService` + backfill + RLS migration, `services/catalog.py`, public catalogue, staff switch; 86 tests OK (RLS tests need PostgreSQL) |
| 2026-09-19 | Phase 3 frontend | DONE in source — catalogue pages, `/services/branches` screen; build OK; not browser-tested |
| 2026-09-19 | Phase 2 backend | DONE — `PortalVerification` + RLS, channel layer, signup/verify, profile, e-mail change, merge keeps account; 124 tests OK |
| 2026-09-19 | Phase 2 frontend | DONE in source — signup page, profile tab; build OK; not browser-tested |
| 2026-09-19 | Phase 1 frontend | DONE in source — landing page, doctors/logo/cover/links on the public clinic sections, employee "show publicly", `/about/media` screen; `vite build` OK; not browser-tested; `dist` not rebuilt |
