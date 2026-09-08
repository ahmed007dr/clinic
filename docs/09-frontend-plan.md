# 09 — Frontend Plan

Status of the frontend, and what is left. Companion to [08-backend-plan.md](08-backend-plan.md).

Markers: **Done** · **Partial** · **Blocked** · **Not started**

---

## What the frontend actually is

Server-rendered **Django templates** — 66 of them across 13 apps. Arabic, RTL throughout (`<html lang="ar" dir="rtl">`), built on a purchased Bootstrap admin theme with jQuery, select2, DataTables and Chart.js. **No JavaScript framework, no build step, no npm, no bundler.** `doc/readme.md` §55 envisions React; nothing of that exists yet.

```
templates/           2   base.html, auth_base.html
billing/            14   employees/  12   appointments/  6
accounts/            6   medical/     6   patients/       5
branches/            4   services/    4   reports/        3
notifications/       2   dashboard/   1   audit/          1
```

---

## 0. Asset pipeline — **Blocked, and it is the first thing to fix**

`base.html` loads twelve vendor assets — Bootstrap, jQuery, select2, DataTables, Chart.js, Material Design Icons, `css/style.css`, logos and images.

**Zero static files are tracked in git.** `static/` does not exist on disk, and `git ls-files static` returns nothing. Every `manage.py check` in this repo emits `staticfiles.W004` because `STATICFILES_DIRS` points at a directory that isn't there — the warning that has appeared on every command throughout this work.

The first commit in the repo's history deletes a `static.zip`, which suggests the theme was distributed as an archive and never committed.

**Consequences:** a fresh clone renders completely unstyled. A new developer cannot see the product. CI cannot verify anything visual. Deployment depends on files that exist only on one machine.

### Audit result (2026-09-08) — the authoritative asset set

`static.zip` **is recoverable from git**: added in `6dc57b9`, removed in `61a6f84`. 5.7 MB, 184 entries, nested under `static/`. Nothing exists on disk.

**It satisfies only 14 of the 24 assets the templates reference.** The gap is not uniform, and three different categories need three different answers:

**a) Genuinely missing and load-bearing — DataTables.** Nine list pages (`user_list`, `audit`, `expense_category_list`, `expense_list`, `billing/list`, `branches/list`, `employee_type_list`, `specialization_list`, `services/list`) call `.DataTable({…})` on real table IDs. It is referenced under **three different paths** (`datatables.net/`, `datatables.net-bs4/`, `datatables/`) and present under none. Those pages currently have no working sort, search or client-side paging.

**b) Redundant references that should be deleted, not satisfied.** `vendor.bundle.base.js` begins with `/*! jQuery v3.6.0` and also contains Bootstrap 5.1.3 and Popper. So:

| Reference | Verdict |
|---|---|
| `vendors/jquery/jquery.min.js` | remove — already in the bundle |
| `vendors/bootstrap/js/bootstrap.bundle.min.js` | remove — already in the bundle |
| `vendors/chart.js/Chart.min.css` | remove — Chart.js ships no stylesheet |
| `vendors/jquery-cookie/jquery.cookie.js` | remove — loaded once, never used |

Adding files to satisfy these would be exactly the duplicated-vendor mistake to avoid.

**c) A version conflict to resolve before adding anything.** The templates ask for the **Bootstrap 4** DataTables integration (`dataTables.bootstrap4.*`) while the bundle ships **Bootstrap 5.1.3**. The correct fix is the Bootstrap 5 build, not the referenced BS4 one.

**Also found:** `billing/expense_update.html` is a rogue template carrying its own duplicate asset stack under a fourth set of paths, including its own jQuery. It is the only user of `vendors/datatables/*` and `jquery-cookie`.

**Archive hygiene:** 138 of its 184 entries are referenced by nothing — theme demo docs, jvectormap, justgage, typeahead, raphael, progressbar, `.DS_Store` files and source maps. Committing the archive wholesale would add ~5 MB of dead weight; the authoritative set is closer to 20 files plus the MDI webfonts.

### Resolution — **Done**

| ID | Item | Status |
|---|---|---|
| FE-001 | `static/` removed from `.gitignore`; **135 files / 9.0 MB now tracked**. Excluded as disposable: `static/docs/` (theme demo), `static/css/maps/` (2.5 MB of source maps), `.DS_Store`, and the generated `staticfiles/` | **Done** |
| FE-001b | DataTables **1.13.8, Bootstrap 5 build** vendored into one path (`vendors/datatables/`); the three reference paths collapsed to one across 10 templates | **Done** |
| FE-001c | Four redundant references removed (6 tags): jQuery and Bootstrap are inside `vendor.bundle.base.js`, Chart.js has no stylesheet, jquery-cookie was never used. `expense_update.html` normalised onto the shared stack | **Done** |
| FE-002 | `manage.py check` reports **no issues (0 silenced)** — the `staticfiles.W004` warning that appeared on every command is gone | **Done** |
| FE-003 | `STATIC_ROOT` set; `collectstatic` copies **267 files** successfully | **Done** |
| FE-005 | 5 tests in `dashboard/tests.py` assert every `{% static %}` reference resolves, that duplicate jQuery/Bootstrap are never reintroduced, and that no template calls a CDN | **Done** |

Reference count fell from **24 to 18, and all 18 resolve.**

**Also fixed while here:** the Arabic DataTables translation was being fetched from `cdn.datatables.net` at runtime on nine pages — the interface degraded to English whenever the clinic's connection did. Now served locally, and a test prevents a CDN call returning.

**And a regression from SEC-011:** `financial_report.html` still carried 30 `branch_id` references in hidden inputs and pagination links after the UUID migration renamed the variable, so the branch filter was silently lost on every page change and tab search. Fixed.

---

## 1. Screens that exist — **Done**

Everything below works, is RTL, and follows one consistent card/form convention.

| Area | Screens | Status |
|---|---|---|
| Auth | login, user list/create/update/delete, settings | **Done** — login now takes **email**, labels updated |
| Patients | list, create, update, delete, detail (+ clinical section) | **Done** |
| Appointments | list, create, update, delete, detail, waiting list | **Done** |
| Billing | payments, expenses, expense categories, financial report | **Done** |
| Employees | employees, types, specializations | **Done** |
| Branches / Services | list, create, update, delete | **Done** |
| Notifications / Audit | list views | **Done** |
| Dashboard | one page with today's totals and a 7-day trend | **Done** (pre-existing) |
| Reports | daily/monthly/annual **email** templates | **Done** (pre-existing) |
| **Medical** | visit form, visit detail, allergy form | **Done** (new) |
| **Prescriptions** | form with inline items, detail, **printable sheet** | **Done** (new) |

Cross-cutting work already applied:

- **FE-005** Branding (`clinic_name` / logo / footer) moved from ~40 duplicated view dicts into one context processor — **Done**
- **FE-006** All 32 `{% url %}` links now carry UUIDs instead of sequential IDs — **Done**
- **FE-007** Appointment screens show `serial_number` instead of the raw database id that was mislabelled as the ticket number — **Done**
- **FE-008** Clinical data is *never rendered* for Reception — the queries are skipped in the view, not hidden in the template — **Done**
- **FE-009** Messages now render on the patient page, which previously swallowed them silently — **Done**

---

## 2. Gaps in the screens that exist — **Not started**

`doc/readme.md` §73 asks for more than CRUD. Measured against it:

| ID | Item | Notes |
|---|---|---|
| FE-010 | **Empty states** | Tables print "لا توجد بيانات" in a cell; no designed empty state anywhere |
| FE-011 | **Loading / skeleton states** | Nothing — every page is a full reload |
| FE-012 | **Error states** | Django's default 404/500 pages; no branded error templates |
| FE-013 | **Mobile / responsive verification** | The theme is responsive in principle; never verified on a real device. doc §72 wants doctor screens mobile-friendly |
| FE-014 | **Accessibility** | No keyboard-focus styling, landmarks or ARIA review |
| FE-015 | **Add/remove medication lines on the prescription formset** | **Done** — see below |
| FE-016 | **Client-side validation and inline field errors** | Errors are dumped as a block at the top of the form |
| FE-017 | **Dashboard** | Single page of counters; doc §47 wants revenue/expense/doctor/service breakdowns |
| FE-018 | **Search and filtering** | Only appointments have a search box; no debouncing anywhere |
| FE-019 | **Print styles beyond the prescription** | The prescription sheet is the only print-designed page |

### FE-015 (2026-09-08) — **Done**

Current state: `inlineformset_factory(extra=3, min_num=1, validate_min=True, can_delete=True)`, rendered as fixed table rows with **no JavaScript at all** on the page.

Two defects, not one:

1. **No way to add a fourth medication.** A doctor prescribing four drugs must save, then re-open and edit.
2. **No way to remove a line while creating.** The `DELETE` checkbox is rendered under `{% if not is_new %}`, so on the create screen the three rows cannot be reduced either.

Approach (no React, no AJAX, formset stays authoritative):

- Render `formset.empty_form` once as a hidden `__prefix__` row template.
- "Add medication" clones it, substitutes the index, and increments `items-TOTAL_FORMS` — the management form remains the single source of truth for the server.
- "Remove" deletes the row from the DOM for unsaved rows and decrements `TOTAL_FORMS`; for saved rows it ticks `DELETE` and hides the row, which is what the formset expects.
- Server-side validation stays authoritative: `validate_min` still rejects an empty prescription regardless of what the client sends.
- `TenantScopedFormMixin` runs when `empty_form` is instantiated, so relation querysets stay request-time evaluated. `PrescriptionItem` has no relation fields today, but the row template must not bypass the form.
- RTL: the add/remove controls sit inside the existing RTL table; no direction-specific CSS needed.

**Implemented as analysed.** `formset.empty_form` is rendered once inside a `<template>`; "إضافة دواء" clones it and re-indexes, "×" removes an unsaved row (re-indexing to close the gap) or ticks `DELETE` and hides a saved one. Rows never reorder, so Django's assumption that the first `INITIAL_FORMS` forms are the saved ones continues to hold. No React, no AJAX, no new dependency.

**Coverage gap closed.** Reception access had been asserted for `prescription_create` and `prescription_detail` only — `prescription_update` and `prescription_print` had no test at all. They were believed safe because both are `@clinical_required`; they are now demonstrated safe, on GET and POST, for all four URLs.

9 tests added: more than three medications, a single medication, blank trailing rows ignored, all-lines-removed refused server-side, deleting a saved line on update, appending a line on update, the row template and add control being present, and the access matrix above.

---

## 3. Screens the backend will need — **Not started**

Each is gated on the corresponding backend work in [08-backend-plan.md](08-backend-plan.md).

| ID | Screens | Gated on |
|---|---|---|
| FE-020 | Procedures, lab results, attachment upload/preview | MED-007/008/009 |
| FE-021 | **Treatment plan builder + session tracker** — the largest new surface: a course of N sessions with per-session status, payment and result | MED-010 |
| FE-022 | Pricing rules, contracts, commission views | FIN-001..003 |
| FE-023 | Invoice view + print, payment capture, refunds | FIN-004/005 |
| FE-024 | Ledger and reconciliation views | FIN-006/007 |
| FE-025 | Queue board (live), availability calendar, resource booking | OPS-003..006 |
| FE-026 | Plans, subscription and entitlement management | SAAS-001/002 |
| FE-027 | **SaaS operator portal** — tenant list, approve/suspend, platform metrics | SAAS-003/006 |
| FE-028 | **Patient portal** — register, book, reschedule, pay, view prescriptions and visits (doc §17). Mobile-first, and an entirely separate audience from the staff app | Most of the backend |

---

## 4. The architectural decision — open

`doc/readme.md` §55–59 describes a React frontend with a central API client. That is **not** what exists, and it is a genuine fork rather than a foregone conclusion.

**Staying with Django templates.** Zero migration cost; one language; server-side rendering keeps tenant scoping and permission checks in one place — the pattern that makes `get_object_or_404` tenant-safe today. Cost: no rich interactivity, full page reloads, and the patient portal (FE-028) would be awkward.

**Moving to React.** Matches the spec, and is the better fit for a patient portal and a live queue board. Cost: **requires the API layer first** (API-001..006, not started), a build pipeline, a second codebase, RTL/Arabic handled again on the client, and every permission rule re-expressed at the API boundary — where a mistake is a data leak rather than a missing button.

**A middle path worth considering:** keep the staff app on templates, add small islands of interactivity where they earn it (queue board, session tracker, formset add-row), and build only the *patient portal* as a separate client against the API. That confines the new surface to the audience that actually needs it.

**No work should start on FE-020..FE-028 until this is settled**, because the answer decides whether each of those is a Django template or a React route.

---

## Recommended order

1. **FE-001/002** — recover the static assets. Nothing visual can be reviewed, tested or deployed reliably until this is fixed, and it is currently the single largest risk on the frontend.
2. **FE-015** — the prescription add-row button; a real defect in work just shipped.
3. **FE-010/012/013** — empty states, branded error pages, and an actual mobile pass.
4. **Settle section 4** before any new screens.
5. Then FE-021 (treatment plans) as the first major new surface, following MED-010.
