# 10 — Deployment runbook

Every step below was rehearsed on 2026-09-09 against a **clean clone of the
committed state**, a virgin PostgreSQL 17 database and a fresh virtualenv built
from `requirements.txt` alone. The commands are what actually ran, not what
ought to work.

What that rehearsal proved: the repository is self-contained. A clone plus a
`.env` produces a working system — migrations apply to an empty database,
`collectstatic` succeeds, a clinic can be onboarded, its administrator can log
in, and every main screen renders.

---

## 0. Read this first — the failure that looks like success

**If the site is served over plain HTTP, every form submission is silently
discarded.**

`SECURE_SSL_REDIRECT` is on whenever `DJANGO_DEBUG=False`. Over HTTP, Django
answers a `POST` with `301 → https://…`. A redirect drops the request body, so
the browser re-issues it as a `GET`: the page reloads, no error appears, and
nothing is saved. Verified in the rehearsal — over HTTP the patient count stayed
at zero; over HTTPS the same request saved.

For a clinic this is the worst possible failure mode: staff enter a patient, the
screen looks normal, and the record does not exist.

So, before handover, exactly one of these must be true:

* **TLS terminates at Django** (it has a real certificate), or
* **TLS terminates at a proxy** and `DJANGO_TRUST_PROXY_SSL_HEADER=True` is set,
  and that proxy sets `X-Forwarded-Proto` **and strips any client-supplied
  copy** — otherwise a client can assert its own connection was secure, or
* `DJANGO_SECURE_SSL_REDIRECT=False`, which is only acceptable while nothing
  real is being entered.

Verify with step 8. Do not skip it.

---

## 1. What must be supplied before starting

These are decisions and secrets, not engineering. Nothing below can proceed
without them.

| | |
|---|---|
| Host | **cPanel shared hosting** (confirmed 2026-09-09). See section 1a |
| Domain + TLS certificate | Drives `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS`, and section 0 |
| PostgreSQL instance | **17** (confirmed). Django 5.2's minimum is 14. The role the application connects as must be **`NOSUPERUSER NOBYPASSRLS`** — see section 4 |
| Python | **3.10 or newer** (Django 5.2 and pillow 12 both require it). Rehearsed on 3.11 |
| SMTP credentials | Reports and notifications. The account rotated under SEC-001 |
| Existing patient data | **None exists** (confirmed 2026-09-09). The system is delivered with the seeded demo dataset; there is no legacy schema and nothing to migrate |


## 1a. cPanel specifics

Four things differ from a plain server, and all four have bitten deployments
before.

**Python version.** cPanel's *Setup Python App* offers a list; pick **3.10 or
newer**. Django 5.2 and pillow 12 both require it, and there is no fallback —
an older interpreter fails at install, not at runtime.

**The entry point.** Setup Python App looks for `passenger_wsgi.py` at the
application root, and this repository ships a working one. It derives its own
path, so it works on any account — unlike the previous version, which hardcoded
`/home/odayscom/src` and had been commented out in its entirety since
2025-09-29, defining no `application` at all. Set the application root to the
clone directory and the application URL to the domain; leave the startup file as
`passenger_wsgi.py`.

**Where files live.** cPanel serves `~/public_html` directly, and only that.
So:

```
DJANGO_STATIC_ROOT=/home/<account>/public_html/static
DJANGO_MEDIA_ROOT=/home/<account>/public_html/media
DJANGO_MEDICAL_ATTACHMENTS_ROOT=/home/<account>/private/attachments
```

**The application clone itself must not be inside `public_html`.** If it is, the
web server will happily serve `.env`, and with it the database password and the
secret key.

**Medical attachments must stay outside `public_html`** — that is the whole
point of `DJANGO_MEDICAL_ATTACHMENTS_ROOT` being separate. A file the web server
can reach has bypassed every permission check the application makes; attachments
are streamed by an authenticated view instead.

**TLS behind Passenger.** cPanel terminates TLS at the web server and proxies to
the application, so Django may see plain HTTP even when the browser is on HTTPS
— which triggers the silent data loss described in section 0, or a redirect
loop. Deploy, enable AutoSSL, then run the section 8 check. **If saving a
patient does nothing, or the site redirects endlessly**, set:

```
DJANGO_TRUST_PROXY_SSL_HEADER=True
```

Only set it once AutoSSL is active and the proxy is genuinely terminating TLS:
it makes Django trust `X-Forwarded-Proto`, and trusting that header on a server
that does not set it lets a client claim its own connection was secure.

## 2. Get the code and build the environment

```bash
git clone <repo> clinic && cd clinic
python -m venv venv
venv/bin/pip install -r requirements.txt          # Windows: venv\Scripts\pip
```

`requirements-dev.txt` adds only Faker, used by `seed_demo`. **Do not install it
in production** — production has no use for a fake-data generator.

## 3. Configure

```bash
cp .env.example .env
```

Fill it in. Every value in the template is a placeholder; none is a real
credential. Generate the secret key rather than inventing one:

```bash
venv/bin/python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

**`PLATFORM_VAULT_KEY`** encrypts every key and password entered in the
developer portal (email, cPanel, payment gateways, Google Drive). Generate it
once and keep it with the database backups — without it those settings cannot
be read back:

```bash
venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Left unset, a key is derived from `DJANGO_SECRET_KEY`, which then cannot be
rotated without re-entering every integration. **No integration key goes in
`.env` or any file**: they are entered only in the developer portal
(«المفاتيح والتكاملات»), each with a test and a production set.

`DJANGO_DEBUG` **must** be `False`. With it on, Django serves `MEDIA_ROOT` with
no authentication at all, and patient photographs become readable by anyone who
guesses a URL.

## 4. The database role

The application connects as a role that is **neither `SUPERUSER` nor
`BYPASSRLS`**. This is not a preference: the row-level security policies that
keep clinics apart are simply skipped for such a role, and the entire isolation
backstop becomes decorative. A test asserts it (`tenants/test_rls.py`), so a
misconfigured deployment fails the suite rather than running unprotected.

```sql
CREATE ROLE clinic_app LOGIN PASSWORD '…' NOSUPERUSER NOBYPASSRLS NOCREATEDB;
CREATE DATABASE clinic OWNER clinic_app;
```

Migrations may be run as the same role — the policies are created by
`tenants.0005`–`0011`, and `FORCE ROW LEVEL SECURITY` means even the table owner
is subject to them.

## 5. Migrate and collect static files

```bash
venv/bin/python manage.py migrate
venv/bin/python manage.py collectstatic --noinput
```

Expect roughly 266 static files. The migrations install the isolation policies
and seed the subscription catalogue (Basic / Professional / Enterprise).

### 5a. The React front end

The React application (`frontend/`) is served at **`/app/`**; the original
server-rendered screens keep working at their own URLs alongside it.

Its compiled build, `frontend/dist/spa/`, is **committed to the repository**,
and `frontend/dist` is in `STATICFILES_DIRS` — so the `collectstatic` above
already deployed it. **No Node is needed on the server**, which matters on
cPanel, where it is not guaranteed.

The consequence is a rule for whoever changes the front end: **rebuild and
commit `dist/` in the same commit as the source change** (`cd frontend && npm ci
&& npm run build`). A stale build is served silently.

If `/app/` shows "واجهة React لم تُبنَ بعد", the build is missing from the clone
— the page names the command that fixes it. Full instructions:
[`frontend/README.md`](../frontend/README.md).

### 5b. The owner portal (`/app/platform`)

Where the platform owner onboards clinics, suspends or reactivates them, and
moves them between plans. Create the owner's account once:

```bash
venv/bin/python manage.py create_platform_admin owner@your-company.example
```

The password is generated and **printed once**. The account belongs to no
clinic: signing in with it opens the owner portal, and every clinic screen and
endpoint refuses it. Everything it does — including merely opening a clinic's
page — is written to that clinic's audit trail.

Onboarding a clinic from the portal is the same as `create_tenant` (section 7):
the clinic, its roles, its first branch, its administrator and a 30-day Basic
trial, in one transaction. The administrator's password is shown once, on
screen.

**Suspending a clinic takes effect immediately**, including for staff who are
already signed in — the API checks the clinic's status on every request, not
only at sign-in.

**Integrations, billing and mailboxes** (docs/06 PLAT-002), all from the portal:

* «المفاتيح والتكاملات»: SMTP, cPanel, Paymob, Fawry, Vodafone Cash (through
  Paymob's wallet integration) and Google Drive — for the whole platform, one
  owner group or one clinic, each with a **test** and a **production** set and
  a switch for which is live. The page shows the callback URL to paste into
  each gateway's dashboard (`https://<host>/api/pay/<gateway>/callback/`).
  Run one real payment in the test environment per gateway before switching to
  production. The platform's gateway keys collect subscriptions; a clinic's
  (or its group's) collect from its patients, and never fall back to the
  platform's.
* «الإيميلات»: creates a mailbox on the platform's cPanel for a group or a
  clinic and can make it that group's/clinic's sender.
* «الاشتراكات والأرصدة» and each group's page: cycle, negotiated price,
  time-limited discounts, invoices, cash/transfer payments, late notes.
  Invoices due are issued by a daily cron entry:

```cron
15 6 * * *  cd ~/app && venv/bin/python manage.py issue_platform_invoices >> ~/logs/invoices.log 2>&1
```

### 5c. The patient portal (`/app/portal/<clinic-slug>/`)

Patients sign in with their **phone number and a password**. There is no
self-registration: the clinic invites each patient from the patient's file
(«دعوة للبوابة»), which produces a single-use link valid for 72 hours. Hand it
over on the clinic's WhatsApp or by SMS; the patient opens it and chooses a
password. A new invitation cancels the previous one; «إيقاف الوصول» signs the
patient out everywhere.

What a patient sees is set in the design (docs/12) and in the clinic's
settings: appointments, prescriptions, payments, treatment progress and
allergies always; lab results and documents only once a doctor presses
«إصدار للمريض»; the diagnosis text only if the clinic turns it on under
الإعدادات → بوابة المرضى. Appointment requests from the portal arrive at
reception with status «طلب من المريض» to confirm.

No SMS provider is needed for this. Patient sessions use their own cookie,
separate from staff sessions, and every clinical record a patient opens is
written to the clinic's audit trail.

### 5d. Roles after this release, and online registration

`migrate` runs `accounts.0007_owner_role`, which turns every existing **Admin** into an **Owner** (the whole group). Admin now means *one clinic's* administrator. After upgrading, review the staff list and demote to Admin anyone who should only manage their own clinic. The account created by `create_tenant` is the group's Owner.

Online self-registration for new patients is **off** for every group. The Owner turns it on under Settings → Patient portal, which then shows the registration link to share. Submissions wait under «طلبات التسجيل» until the front desk confirms, merges or rejects them.

## 6. Check the deployment

```bash
venv/bin/python manage.py check --deploy
```

**One warning is expected and correct**: `security.W004`, that
`SECURE_HSTS_SECONDS` is unset. HSTS is deliberately opt-in — browsers cache it
for its `max-age` and will then refuse plain HTTP to the domain and every
subdomain for that whole period, ignoring anything the server later sends. Turn
it on once HTTPS is confirmed everywhere, starting small:

```
DJANGO_SECURE_HSTS_SECONDS=3600      # raise to 31536000 after a week of calm
DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=True
```

**Any other warning is a real finding.** Do not silence it.

## 7. Onboard the first clinic

```bash
venv/bin/python manage.py create_tenant "اسم العيادة" \
    --slug clinic-slug --admin-email admin@clinic.example \
    --branch "الفرع الرئيسي" --branch-code MAIN
```

This creates the tenant, its roles (Admin, Reception, Doctor), the Doctor
employee type, the first branch, the administrator account, and a Basic trial
subscription. **The generated password is printed once and is not recoverable** —
capture it before closing the terminal, and hand it over out of band.

A non-ASCII name needs `--slug`, because `slugify()` returns an empty string for
Arabic and a tenant with a blank slug is unusable.

## 8. Verify before handing over

Do these against the real URL, over HTTPS, in a browser.

1. **Log in** as the clinic administrator.
2. **Register a patient, then reload the list and confirm it is there.** This is
   the section 0 check. If the patient does not appear, TLS is misconfigured and
   nothing is being saved.
3. Open the patient, record a visit, issue a prescription, **print it** — this
   also confirms the Arabic PDF font is working (FE-016). Arabic must be joined
   and right-to-left, not boxes or disconnected letters.
4. Export the patient list as **PDF** and as **Excel**; open both.
5. Log in as a **Reception** account and confirm no diagnosis is visible.
6. Check `/admin/` loads for a superuser. Tenant-owned models are deliberately
   absent from it (ADMIN-002) — that is expected, not a fault.

## 9. Load the demo dataset

There is no existing data and no legacy schema, so the system is delivered with
a seeded dataset:

```bash
venv/bin/python manage.py seed_demo --reset
```

This creates two clinics with Arabic patients, appointments, visits,
prescriptions, treatment plans, sessions, procedures, lab results and payments,
plus Owner (`admin@…`), Admin (`clinicadmin@…`), Reception and Doctor logins for
each, all on `.local` addresses. The password is **generated per run and printed
once** at the end — it is not stored readable anywhere. Accounts that already
existed keep the password they had. (`--password <pw>` fixes it, for a local
machine only.)

### 9a. Before the clinic enters real data: switch the demo logins off

Anyone who saw the seeder's output can sign in with those accounts, so they must
not survive the handover:

```bash
venv/bin/python manage.py disable_demo_accounts --dry-run   # lists them
venv/bin/python manage.py disable_demo_accounts
```

The accounts are deactivated, not deleted — the demo records still point at
them — and any session they had stops on its next request. Real staff accounts
are never touched: the command matches only the exact `<role>@<slug>.local`
addresses the seeder creates.

It runs on a production install: `Faker` is a development dependency and is
deliberately absent from `requirements.txt`, so the seeder falls back to a
built-in Arabic generator and says which it used. **Do not install
`requirements-dev.txt` on the server** to get Faker — it is not needed.

`--reset` clears the seeded data first, so it is safe to re-run. **It deletes
everything except the `dr-ahmed` tenant**, which makes it exactly the wrong
command to run once the clinic has entered real records. Once real use begins,
stop using it.

If data ever does need importing from elsewhere, `manage.py
audit_data_compatibility` reports values SQLite accepts and PostgreSQL rejects.
It is read-only and mutates nothing.

## 10. Ongoing

* **Backups.** Nothing in this repository backs anything up. A managed
  PostgreSQL instance with point-in-time recovery is the least work; whatever is
  chosen, restore it once before relying on it.
* **`private/`** holds medical attachments and is outside `MEDIA_ROOT` on
  purpose. It is not in version control and **must** be included in backups —
  losing it loses patient documents. It must never be served by the web server;
  attachments are streamed by an authenticated view.
* **Secret rotation.** `DJANGO_SECRET_KEY` invalidates all sessions when
  changed, which is the point.
* **Scheduled reports** (`reports/views.py`) exist but nothing invokes them —
  they need a cron entry or equivalent, and none is configured.

## 11. Known gaps at handover

Honest list. None of these blocks day-to-day clinical use.

| Gap | Impact |
|---|---|
| No live payment gateway | Subscription billing is manual — record transfers out of band. The clinic-facing patient billing is unaffected and works |
| Cross-tenant reporting | Platform totals need a per-tenant loop; RLS means an unbound aggregate returns nothing rather than a wrong number |
| No appointment conflict check | Two bookings for the same doctor at the same time are both accepted; reception checks the doctor's list before booking |
| No SMS / WhatsApp | Portal invitations and appointment confirmations are sent by hand; there is no provider |
| Demo accounts | Present on a seeded install until `disable_demo_accounts` is run — see §9a |
| Scheduled reports unwired | See section 10 |
| `passenger_wsgi.py` | Inert and unused. `project/wsgi.py` is the real entry point; delete the former or repair it deliberately |
