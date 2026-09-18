"""Demo data for local development and manual testing.

Seeds two tenants on purpose. A single tenant proves nothing about isolation —
with two, you can log in as one clinic and confirm the other's patients,
services and revenue are genuinely unreachable.

    python manage.py seed_demo
    python manage.py seed_demo --reset     # wipe demo data first
    python manage.py seed_demo --password <pw>   # fixed password, local work only

The demo accounts get a random password per run, printed once. A fixed,
published password on a server that is reachable from the internet is a door
anyone can open; before real use, `manage.py disable_demo_accounts` switches
the demo logins off altogether.
"""

import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import ClinicRole
from appointments.models import Appointment
from audit.models import AuditLog
from billing.models import (
    CashShift,
    DiscountCoupon,
    DoctorCommission,
    DoctorServiceRate,
    Expense,
    ExpenseCategory,
    Payment,
    PaymentMethod,
)
from billing.shifts import summarize
from branches.models import Branch
from employees.models import Employee, EmployeeType, SalaryType, Specialization
from notifications.models import Notification
from medical.models import (
    Allergy,
    LabResult,
    Prescription,
    PrescriptionItem,
    Procedure,
    TreatmentPlan,
    TreatmentSession,
    Visit,
)
from patients.models import Patient
from portal.models import PatientAccount, PortalInvitation, PortalLoginCode, PortalSession
from services.models import Service
from subscriptions.models import Plan, Subscription
from tenants.context import tenant_context
from tenants.models import SerialCounter, Tenant
from django.utils.crypto import get_random_string

from tenants.provisioning import PASSWORD_ALPHABET, provision_tenant_defaults

from ._demo_data import get_generator

User = get_user_model()


COMPLAINTS = ["حكة وطفح جلدي", "تساقط الشعر", "بقع داكنة بالوجه", "حب الشباب", "جفاف الجلد"]
DIAGNOSES = ["التهاب جلدي تحسسي", "أكزيما", "حب شباب متوسط", "تصبغات جلدية", "صدفية خفيفة"]
ALLERGENS = ["البنسلين", "الأسبرين", "اليود", "اللاتكس", "السلفا"]
REACTIONS = ["طفح جلدي", "تورم", "ضيق تنفس", "حكة شديدة"]
PROCEDURES = ["استئصال شامة", "كي بالتبريد", "خزعة جلدية", "تفريغ خراج", "حقن موضعي"]
BODY_SITES = ["الساعد الأيمن", "الظهر", "فروة الرأس", "الوجه - الخد الأيسر", "الساق اليسرى"]
# (test, unit, reference range, a normal value, an out-of-range value)
LAB_TESTS = [
    ("صورة دم كاملة", "g/dL", "12.0 - 15.5", "13.4", "9.1"),
    ("سكر صائم", "mg/dL", "70 - 99", "88", "162"),
    ("وظائف الكبد ALT", "U/L", "7 - 56", "24", "118"),
    ("فيتامين د", "ng/mL", "30 - 100", "42", "11"),
]
SPECIMENS = ["دم وريدي", "بول", "مسحة جلدية"]
MEDICATIONS = [
    ("كريم هيدروكورتيزون", "1%", "مرتين يومياً", "أسبوعين", "موضعي على المنطقة المصابة"),
    ("لوراتادين", "10 مجم", "مرة يومياً", "10 أيام", "قبل النوم"),
    ("دوكسيسيكلين", "100 مجم", "مرتين يومياً", "شهر", "بعد الأكل"),
    ("مرطب طبي", "-", "عند اللزوم", "مستمر", "بعد الاستحمام"),
]

# Two demo patients per clinic with a portal login (password = the run's).
# Fixed phone and email so they can be written down and typed: the portal signs
# in by phone (or emails a code). Their email is on a `.local` domain, so a
# sign-in code cannot actually arrive -- put a real address on the record to try
# that. `disable_demo_accounts` switches these logins off with the staff ones.
PORTAL_PATIENTS = [
    # (name, phone, email local part, has a full record)
    ("منى السيد (عميل تجريبي)", "01099000001", "patient1", True),
    ("خالد عمر (عميل تجريبي)", "01099000002", "patient2", False),
]

TENANTS = [
    {
        "name": "Dr-ahmed",
        "slug": "dr-ahmed",
        "branches": [("سوهاج", "SOH"), ("أسيوط", "ASY")],
        "services": [
            ("Eximer 120", "جلسة ليزر Eximer 120", 1200),
            ("Eximer 160", "جلسة ليزر Eximer 160", 1600),
            ("Q switch 800", "جلسة ليزر Q switch 800", 800),
            ("كشف عام", "كشف عيادة عام", 300),
        ],
        "patients": 40,
        "employees": 8,
        "appointments": 60,
    },
    {
        "name": "Nile Clinic",
        "slug": "nile-clinic",
        "branches": [("القاهرة", "CAI")],
        "services": [
            ("استشارة جلدية", "استشارة أمراض جلدية", 450),
            ("تنظيف بشرة", "جلسة تنظيف بشرة عميق", 700),
        ],
        "patients": 15,
        "employees": 3,
        "appointments": 20,
    },
]


class Command(BaseCommand):
    help = "Seed two demo tenants with realistic Arabic data for local testing."
    reset_passwords = False

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing demo data before seeding.",
        )
        parser.add_argument(
            "--password",
            default="",
            help="Password for accounts created by this run. Default: random, "
            "printed once. Use a fixed one only on a local machine.",
        )
        parser.add_argument(
            "--reset-passwords",
            action="store_true",
            help="With --password: also set that password on demo accounts that "
            "already exist, so a showcase copy keeps one known password across "
            "re-runs.",
        )

    def handle(self, *args, **options):
        # Faker is a development dependency and is deliberately absent from a
        # production install, but the demo dataset is what the system ships
        # with — so the seeder has to run there too. _demo_data supplies the
        # handful of generators this command needs when Faker is missing.
        self.fake, source = get_generator(20260908)
        random.seed(20260908)  # reproducible runs
        self.stdout.write(f"Generating demo data using: {source}")

        # get_random_string draws from `secrets`, so the random.seed above —
        # there for reproducible data — does not make the password predictable.
        self.password = options["password"] or get_random_string(
            14, allowed_chars=PASSWORD_ALPHABET
        )
        self.created_accounts = []
        self.created_portal = []
        self.reset_passwords = options["reset_passwords"]
        if self.reset_passwords and not options["password"]:
            raise CommandError("--reset-passwords needs --password: a random one would lock everyone out.")

        if options["reset"]:
            self._reset()

        # The demo doctors have made-up addresses and the mail settings are the
        # real ones: generating data must never email anyone.
        from billing.notify import muted

        summaries = []
        with muted():
            for spec in TENANTS:
                summaries.append(self._seed_tenant(spec))

        self._report(summaries)

    # ------------------------------------------------------------------ reset

    def _reset(self):
        self.stdout.write("Clearing existing data...")
        with transaction.atomic():
            # Tenant-owned tables are cleared one tenant at a time. Under
            # PostgreSQL RLS an unbound DELETE matches nothing and reports
            # success, so a blanket .all().delete() would quietly clear no rows
            # and leave the seeder to collide with the data it thought it had
            # removed. `all_objects` is not an escape hatch at this layer.
            for tenant in Tenant.objects.all():
                with tenant_context(tenant):
                    self._clear_rows_for_current_tenant()

            SerialCounter.objects.all().delete()
            User.objects.filter(is_superuser=False).delete()

            # Last: every delete above fires the audit signal and writes new
            # AuditLog rows pointing at the tenant, and AuditLog.tenant is
            # PROTECT — so clearing it any earlier just leaves fresh rows behind.
            AuditLog.objects.all().delete()
            Tenant.objects.exclude(slug="dr-ahmed").delete()

    def _clear_rows_for_current_tenant(self):
        # Order matters: dependants before the rows they point at.
        Payment.all_objects.all().delete()
        Expense.all_objects.all().delete()
        # Cash shifts PROTECT their user and branch; they go once the money
        # filed under them has.
        CashShift.all_objects.all().delete()
        # Doctor shares and contracts PROTECT/CASCADE from the doctor record.
        DiscountCoupon.all_objects.all().delete()
        DoctorCommission.all_objects.all().delete()
        DoctorServiceRate.all_objects.all().delete()
        # Clinical records first: Visit.patient, Allergy.patient,
        # TreatmentPlan.patient, TreatmentSession.patient and
        # Procedure.patient/.visit and LabResult.patient are all PROTECT, so
        # patients and visits
        # cannot be cleared while any of these exist. Sessions before plans,
        # and procedures before visits, for the same reason.
        # Subscriptions must go here, inside the per-tenant binding, not with
        # the platform-level rows below. Tenant.delete() cannot find them
        # otherwise: Django's deletion collector reads related rows through
        # `all_objects`, and under RLS an unbound query sees nothing — so the
        # collector concludes there is nothing PROTECTing the tenant, deletes
        # it, and the database raises a raw foreign-key violation instead of
        # the ProtectedError the ORM would have given.
        Subscription.all_objects.all().delete()
        LabResult.all_objects.all().delete()
        Procedure.all_objects.all().delete()
        TreatmentSession.all_objects.all().delete()
        TreatmentPlan.all_objects.all().delete()
        PrescriptionItem.all_objects.all().delete()
        Prescription.all_objects.all().delete()
        Visit.all_objects.all().delete()
        Allergy.all_objects.all().delete()
        Appointment.all_objects.all().delete()
        Notification.all_objects.all().delete()
        # Portal logins hang off patients; they go first so nothing PROTECTs the tenant.
        PortalLoginCode.all_objects.all().delete()
        PortalSession.all_objects.all().delete()
        PortalInvitation.all_objects.all().delete()
        PatientAccount.all_objects.all().delete()
        Patient.all_objects.all().delete()
        Employee.all_objects.all().delete()
        Service.all_objects.all().delete()
        ExpenseCategory.all_objects.all().delete()
        PaymentMethod.all_objects.all().delete()
        Specialization.all_objects.all().delete()
        SalaryType.all_objects.all().delete()
        # User.role and User.branch are SET_NULL, so the users these rows
        # belong to survive this and are removed by the caller.
        EmployeeType.all_objects.all().delete()
        ClinicRole.all_objects.all().delete()
        Branch.all_objects.all().delete()


    def _subscribe_to_demo_plan(self, tenant):
        """Put demo tenants on Professional rather than the Basic trial that
        provisioning gives a real new clinic.

        Otherwise the demo data contradicts its own plan: Basic allows one
        branch and this seeder creates two, so the fixture would start out over
        its limit. Professional (3 branches, 25 staff, 5000 patients) fits what
        is seeded, so the entitlement checks can be exercised honestly — try
        adding a fourth branch and the limit fires for the right reason.
        """
        professional = Plan.objects.filter(code="professional").first()
        if professional is None:
            return
        with tenant_context(tenant):
            Subscription.all_objects.filter(tenant=tenant).update(plan=professional)

    # ------------------------------------------------------------------- seed

    def _seed_tenant(self, spec):
        fake = self.fake

        tenant, created = Tenant.objects.get_or_create(
            slug=spec["slug"],
            defaults={"name": spec["name"], "status": Tenant.Status.ACTIVE},
        )
        provision_tenant_defaults(tenant)
        self._subscribe_to_demo_plan(tenant)

        # Inside this block, plain .objects queries are scoped to this tenant.
        with tenant_context(tenant):
            branches = [
                Branch.objects.get_or_create(
                    tenant=tenant, code=code,
                    defaults={
                    "name": name, "address": fake.address(), "phone": fake.phone_number()[:32],
                    # What the patient portal's "About" tab shows.
                    "map_url": f"https://maps.google.com/?q={code}",
                    "working_hours": "السبت – الخميس: ٩ ص – ٩ م\nالجمعة: إجازة",
                    "about_text": f"فرع {name}: كشف واستشارات وجلسات ليزر بأحدث الأجهزة على يد أطباء متخصصين.",
                },
                )[0]
                for name, code in spec["branches"]
            ]

            owner_role = ClinicRole.objects.get(name="Owner")
            admin_role = ClinicRole.objects.get(name="Admin")
            reception_role = ClinicRole.objects.get(name="Reception")
            doctor_role = ClinicRole.objects.get(name="Doctor")
            doctor_type = EmployeeType.objects.get(name="Doctor")
            nurse_type = EmployeeType.objects.get_or_create(
                tenant=tenant, name="Nurse", defaults={"description": "Nursing staff"}
            )[0]

            users = [
                # The group owner (every clinic) and one clinic admin (the first clinic).
                self._user(tenant, f"admin@{spec['slug']}.local", "admin", owner_role, branches[0]),
                self._user(tenant, f"clinicadmin@{spec['slug']}.local", "clinicadmin", admin_role, branches[0]),
                self._user(tenant, f"reception@{spec['slug']}.local", "reception", reception_role, branches[0]),
                # Log in as this one to see the clinical screens; the reception
                # account is the one to log in as to confirm it cannot.
                self._user(tenant, f"doctor@{spec['slug']}.local", "doctor", doctor_role, branches[0]),
            ]

            salary_types = [
                SalaryType.objects.get_or_create(tenant=tenant, name=n)[0]
                for n in ("شهري", "بالساعة")
            ]
            specializations = [
                Specialization.objects.get_or_create(
                    tenant=tenant, name=n, defaults={"description": fake.sentence()}
                )[0]
                for n in ("جلدية", "تجميل", "ليزر")
            ]

            services = [
                Service.objects.get_or_create(
                    tenant=tenant, name=name,
                    defaults={
                        "description": desc,
                        "base_price": Decimal(price),
                        "specialization": random.choice(specializations),
                    },
                )[0]
                for name, desc, price in spec["services"]
            ]

            payment_methods = [
                PaymentMethod.objects.get_or_create(
                    tenant=tenant, name=n, defaults={"description": fake.sentence()}
                )[0]
                for n in ("نقدي", "فيزا", "تأمين")
            ]
            expense_categories = [
                ExpenseCategory.objects.get_or_create(
                    tenant=tenant, name=n, defaults={"description": fake.sentence()}
                )[0]
                for n in ("رواتب", "إيجار", "كهرباء", "مستلزمات")
            ]

            employees = []
            for i in range(spec["employees"]):
                employee = Employee.objects.create(
                    tenant=tenant,
                    name=fake.name(),
                    employee_type=doctor_type if i < max(2, spec["employees"] // 2) else nurse_type,
                    branch=random.choice(branches),
                    national_id=fake.unique.numerify(text="##############"),
                    phone1=fake.phone_number()[:32],
                    email=fake.unique.email(),
                    hire_date=fake.date_between(start_date="-3y", end_date="today"),
                    salary_type=random.choice(salary_types),
                    salary_value=Decimal(random.randint(4000, 18000)),
                )
                employee.specializations.set(random.sample(specializations, k=random.randint(1, 2)))
                employees.append(employee)

            doctors = [e for e in employees if e.employee_type_id == doctor_type.id]

            # The demo doctor account *is* the first doctor, in the account's
            # own clinic: a doctor sees only their own patients
            # (accounts.roles), so an unlinked demo login would show nothing.
            demo_doctor = doctors[0]
            if demo_doctor.branch_id != branches[0].id:
                demo_doctor.branch = branches[0]
                demo_doctor.save(update_fields=["branch"])
            users[3].employee = demo_doctor
            users[3].save(update_fields=["employee"])

            # Every doctor is under contract for every service, at the
            # catalogue price: the booking form offers a doctor's contracted
            # services only, so a doctor with no contract line offers nothing.
            for doctor in doctors:
                for service in services:
                    DoctorServiceRate.objects.get_or_create(
                        tenant=tenant, doctor=doctor, service=service,
                        defaults={"commission_percent": Decimal("40")},
                    )

            patients = [
                Patient.objects.create(
                    tenant=tenant,
                    name=fake.name(),
                    national_id=fake.unique.numerify(text="##############"),
                    gender=random.choice(["male", "female"]),
                    birth_date=fake.date_of_birth(minimum_age=18, maximum_age=80),
                    phone1=fake.phone_number()[:32],
                    email=fake.unique.email(),
                    marital_status=random.choice(["single", "married"]),
                    address=fake.address(),
                    branch=random.choice(branches),
                )
                for _ in range(spec["patients"])
            ]

            appointments, payments, coupons, shifts = self._seed_bookings_and_money(
                tenant, spec, branches, users, patients, doctors, services,
                specializations, payment_methods,
            )

            # Clinical records for roughly a third of the visits that happened —
            # a booking that was completed, or where the patient is with the
            # doctor now. Entering already opened a visit (medical/checkin.py),
            # so this fills that one in rather than adding a second.
            happened = [a for a in appointments if a.status in ("completed", "entered")]
            visits = []
            for appointment in happened[: max(3, len(happened) // 3)]:
                visit, _ = Visit.objects.update_or_create(
                    tenant=tenant,
                    appointment=appointment,
                    defaults=dict(
                        patient=appointment.patient,
                        doctor=appointment.doctor,
                        branch=appointment.branch,
                        visit_date=appointment.scheduled_date,
                        chief_complaint=random.choice(COMPLAINTS),
                        examination=fake.sentence(),
                        diagnosis=random.choice(DIAGNOSES),
                        treatment_plan=fake.sentence(),
                        created_by=users[2],
                    ),
                )
                visits.append(visit)

            prescriptions = []
            for visit in visits:
                if random.random() > 0.75:
                    continue
                prescription = Prescription.objects.create(
                    tenant=tenant, visit=visit, patient=visit.patient,
                    doctor=visit.doctor, issued_at=visit.visit_date,
                    created_by=users[2],
                )
                for medication, dosage, frequency, duration, instructions in random.sample(
                    MEDICATIONS, k=random.randint(1, 3)
                ):
                    PrescriptionItem.objects.create(
                        tenant=tenant, prescription=prescription,
                        medication=medication, dosage=dosage, frequency=frequency,
                        duration=duration, instructions=instructions,
                    )
                prescriptions.append(prescription)

            allergies = []
            for patient in patients[:5]:
                substance = random.choice(ALLERGENS)
                if not Allergy.objects.filter(patient=patient, substance=substance).exists():
                    allergies.append(
                        Allergy.objects.create(
                            tenant=tenant, patient=patient, substance=substance,
                            reaction=random.choice(REACTIONS),
                            severity=random.choice([s[0] for s in Allergy.Severity.choices]),
                            recorded_by=users[2],
                        )
                    )

            # Treatment plans, with a partly-delivered course each — so the
            # "3 مكتملة من 6" progress on the plan page shows something real,
            # and so a quantity-priced session (doc §29) exists to look at.
            plans, sessions = [], []
            for visit in visits[:3]:
                service = random.choice(services)
                plan = TreatmentPlan.objects.create(
                    tenant=tenant,
                    patient=visit.patient,
                    visit=visit,
                    doctor=visit.doctor,
                    branch=visit.branch,
                    service=service,
                    title=f"{service.name} - برنامج علاجي",
                    planned_sessions=random.randint(4, 8),
                    start_date=visit.visit_date.date(),
                    created_by=users[2],
                )
                plans.append(plan)

                delivered = random.randint(1, plan.planned_sessions - 1)
                for index in range(delivered + 1):
                    done = index < delivered
                    quantity = random.choice([1, 1, 1, 25])  # occasional pulse count
                    sessions.append(
                        TreatmentSession.objects.create(
                            tenant=tenant,
                            plan=plan,
                            patient=plan.patient,
                            doctor=plan.doctor,
                            branch=plan.branch,
                            service=service,
                            scheduled_date=visit.visit_date + timedelta(days=7 * index),
                            performed_at=(
                                visit.visit_date + timedelta(days=7 * index) if done else None
                            ),
                            status=(
                                TreatmentSession.Status.COMPLETED
                                if done
                                else TreatmentSession.Status.SCHEDULED
                            ),
                            quantity=quantity,
                            unit_price=service.base_price,
                            # Kept well inside the line total — the database
                            # constraint refuses a discount larger than it.
                            discount=Decimal(random.choice([0, 0, 50])),
                            result=fake.sentence() if done else "",
                            created_by=users[2],
                        )
                    )

            # A procedure on some of the visits, one of them with a recorded
            # complication so the warning path is visible in demo data.
            procedures = []
            for index, visit in enumerate(visits[:4]):
                service = random.choice(services)
                procedures.append(
                    Procedure.objects.create(
                        tenant=tenant,
                        visit=visit,
                        patient=visit.patient,
                        doctor=visit.doctor,
                        branch=visit.branch,
                        service=service,
                        name=random.choice(PROCEDURES),
                        body_site=random.choice(BODY_SITES),
                        performed_at=visit.visit_date,
                        status=Procedure.Status.COMPLETED,
                        quantity=1,
                        unit_price=service.base_price,
                        discount=Decimal(0),
                        findings=fake.sentence(),
                        outcome=fake.sentence(),
                        complications="احمرار موضعي خفيف" if index == 0 else "",
                        created_by=users[2],
                    )
                )

            # A few lab results, including one abnormal-and-unacknowledged so
            # the "needs attention" path is visible in demo data.
            lab_results = []
            for index, visit in enumerate(visits[:5]):
                test, unit, ref, normal, abnormal = random.choice(LAB_TESTS)
                out_of_range = index == 0
                lab_results.append(
                    LabResult.objects.create(
                        tenant=tenant,
                        patient=visit.patient,
                        visit=visit,
                        ordered_by=visit.doctor,
                        branch=visit.branch,
                        test_name=test,
                        specimen=random.choice(SPECIMENS),
                        lab_name="معمل المركز",
                        value=abnormal if out_of_range else normal,
                        unit=unit,
                        reference_range=ref,
                        flag=LabResult.Flag.ABNORMAL if out_of_range else LabResult.Flag.NORMAL,
                        status=LabResult.Status.RESULTED,
                        ordered_at=visit.visit_date,
                        created_by=users[2],
                    )
                )

            portal_accounts = self._seed_portal_patients(
                tenant, branches, users, demo_doctor, services, specializations, payment_methods
            )

            expenses = list(Expense.objects.filter(tenant=tenant))

        return {
            "tenant": tenant,
            "slug": spec["slug"],
            "branches": len(branches),
            "employees": len(employees),
            "patients": len(patients),
            "services": len(services),
            "appointments": len(appointments),
            "payments": len(payments),
            "expenses": len(expenses),
            "coupons": len(coupons),
            "shifts": len(shifts),
            "visits": len(visits),
            "allergies": len(allergies),
            "prescriptions": len(prescriptions),
            "plans": len(plans),
            "sessions": len(sessions),
            "procedures": len(procedures),
            "lab_results": len(lab_results),
            "portal": portal_accounts,
        }

    # ---------------------------------------------------------- portal patients

    def _seed_portal_patients(
        self, tenant, branches, users, doctor, services, specializations, payment_methods
    ):
        """Patients who can sign in to the portal, so it can be shown and tried.

        The first has something in every tab: a visit with a diagnosis, a
        prescription, one released lab result (and one still held back, to show
        the release rule), an allergy, a treatment course in progress, and
        today's booking waiting in the queue -- part paid, so it has a ticket, a
        turn and a balance. The second is a new patient with an empty portal.
        """
        from billing.pricing import price_for

        main = branches[0]
        reception, demo_doctor_user = users[2], users[3]
        service = services[0]
        now = timezone.now()
        accounts = []

        for name, phone, local, full in PORTAL_PATIENTS:
            email = f"{local}@{tenant.slug}.local"
            patient, created = Patient.objects.get_or_create(
                tenant=tenant, phone1=phone,
                defaults=dict(
                    name=name, email=email, branch=main,
                    gender="female" if full else "male",
                    birth_date=date(1990, 5, 17),
                    national_id=self.fake.unique.numerify(text="##############"),
                    marital_status="single",
                ),
            )
            account, account_created = PatientAccount.objects.get_or_create(
                patient=patient, defaults={"tenant": tenant}
            )
            if account_created or self.reset_passwords:
                account.set_password(self.password)
                account.is_active = True
                account.failed_logins = 0
                account.locked_until = None
                account.save()
                self.created_portal.append(phone)
            accounts.append({"name": name, "phone": phone, "email": email, "full": full})

            # The record is built once; a re-run of the seeder leaves it alone.
            if not full or not created:
                continue

            past = Appointment.objects.create(
                tenant=tenant, patient=patient, doctor=doctor, branch=main, service=service,
                specialization=service.specialization or random.choice(specializations),
                status="completed", scheduled_date=now - timedelta(days=10), price=0,
                notes="متابعة", created_by=reception,
            )
            visit = Visit.objects.create(
                tenant=tenant, appointment=past, patient=patient, doctor=doctor, branch=main,
                visit_date=past.scheduled_date, chief_complaint="حكة وطفح جلدي",
                examination="احمرار وجفاف بالساعدين", diagnosis="التهاب جلدي تحسسي",
                treatment_plan="مرطب وكريم موضعي", follow_up_date=(now + timedelta(days=7)).date(),
                created_by=reception,
            )
            prescription = Prescription.objects.create(
                tenant=tenant, visit=visit, patient=patient, doctor=doctor,
                issued_at=visit.visit_date, created_by=reception,
            )
            for medication, dosage, frequency, duration, instructions in MEDICATIONS[:3]:
                PrescriptionItem.objects.create(
                    tenant=tenant, prescription=prescription, medication=medication,
                    dosage=dosage, frequency=frequency, duration=duration, instructions=instructions,
                )
            Allergy.objects.create(
                tenant=tenant, patient=patient, substance="البنسلين", reaction="طفح جلدي",
                severity=Allergy.Severity.MODERATE, recorded_by=reception,
            )
            for test_name, unit, ref, normal, abnormal in LAB_TESTS[:2]:
                shown = test_name == LAB_TESTS[0][0]
                LabResult.objects.create(
                    tenant=tenant, patient=patient, visit=visit, ordered_by=doctor, branch=main,
                    test_name=test_name, specimen="دم وريدي", lab_name="معمل المركز",
                    value=normal if shown else abnormal, unit=unit, reference_range=ref,
                    flag=LabResult.Flag.NORMAL if shown else LabResult.Flag.ABNORMAL,
                    status=LabResult.Status.RESULTED, ordered_at=visit.visit_date,
                    # The second is left unreleased: the doctor has not called yet.
                    released_to_patient=shown, released_at=now if shown else None,
                    released_by=demo_doctor_user if shown else None, created_by=reception,
                )
            plan = TreatmentPlan.objects.create(
                tenant=tenant, patient=patient, visit=visit, doctor=doctor, branch=main,
                service=service, title=f"{service.name} - برنامج علاجي", planned_sessions=6,
                start_date=visit.visit_date.date(), created_by=reception,
            )
            for index in range(3):
                done = index < 2
                TreatmentSession.objects.create(
                    tenant=tenant, plan=plan, patient=patient, doctor=doctor, branch=main,
                    service=service, scheduled_date=visit.visit_date + timedelta(days=7 * index),
                    performed_at=visit.visit_date + timedelta(days=7 * index) if done else None,
                    status=TreatmentSession.Status.COMPLETED if done else TreatmentSession.Status.SCHEDULED,
                    quantity=1, unit_price=service.base_price, discount=Decimal(0),
                    result="تحسن ملحوظ" if done else "", created_by=reception,
                )

            # Today, waiting, part paid: a ticket number, a turn, a balance.
            price = price_for(doctor, service) or service.base_price
            today_booking = Appointment.objects.create(
                tenant=tenant, patient=patient, doctor=doctor, branch=main, service=service,
                specialization=service.specialization or random.choice(specializations),
                status="waiting", scheduled_date=now, price=price, created_by=reception,
            )
            shift = CashShift.objects.filter(
                user=reception, branch=main, status=CashShift.Status.OPEN
            ).first()
            if shift is not None:
                Payment.objects.create(
                    tenant=tenant, appointment=today_booking, patient=patient,
                    method=random.choice(payment_methods),
                    receipt_number="R-" + SerialCounter.next_serial(tenant.id, "receipt", now.date()),
                    amount=(Decimal(price) / 2).quantize(Decimal("0.01")),
                    branch=main, shift=shift, created_by=reception,
                )
            # And a request the patient made from the portal, awaiting reception.
            Appointment.objects.create(
                tenant=tenant, patient=patient, doctor=doctor, branch=main, service=service,
                status="requested", scheduled_date=now + timedelta(days=3), price=price,
                notes="[طلب من بوابة المرضى] متابعة",
            )
        return accounts

    # ------------------------------------------------------------ bookings, money

    def _seed_bookings_and_money(
        self, tenant, spec, branches, users, patients, doctors, services,
        specializations, payment_methods,
    ):
        """Bookings, payments, shifts, expenses and coupons — the way the
        system now works, not as loose rows.

        * Every payment belongs to a booking and sits in a cash shift of the
          person who took it; expenses sit in shifts too. A shift starts from
          zero. Past days' shifts are closed with their frozen summary; the
          reception account's shift for today is open, so the live shift
          screen has something to show.
        * A patient is in with the doctor ("entered") only if the booking is
          paid in full — net of any coupon. Today's queue also has patients
          with a balance still owing, one not paid at all, and future
          bookings paid in advance, in part, or not yet.
        * Coupons in every state: spent on a completed booking, still
          available, expired, cancelled.
        """
        fake = self.fake
        owner, clinic_admin, reception = users[0], users[1], users[2]
        now = timezone.now()
        today = now.date()
        main = branches[0]
        cent = Decimal("0.01")

        def at(day, hour, minute=0):
            moment = datetime.combine(day, time(hour, minute))
            return timezone.make_aware(moment) if settings.USE_TZ else moment

        # The desk of the first clinic is reception's; the owner, who sees every
        # clinic, took the money at the others.
        def cashier_for(branch):
            return reception if branch.pk == main.pk else owner

        # Today's shift opened a few hours ago — but never before today began: a
        # shift is one day's, and its bookings and expenses are dated by it.
        opened_today = max(now - timedelta(hours=3), at(today, 0, 0))
        first_booking = opened_today + timedelta(minutes=1)

        shifts = {}

        def shift_on(branch, day):
            cashier = cashier_for(branch)
            key = (cashier.pk, branch.pk, day)
            if key not in shifts:
                is_today = day == today
                shift = CashShift.objects.create(
                    tenant=tenant, user=cashier, branch=branch,
                    status=CashShift.Status.OPEN if is_today and cashier == reception else CashShift.Status.CLOSED,
                )
                opened = opened_today if is_today else at(day, 8)
                updates = {"opened_at": opened}
                if shift.status == CashShift.Status.CLOSED:
                    updates.update(closed_at=at(day, 20), closed_by=cashier)
                CashShift.all_objects.filter(pk=shift.pk).update(**updates)
                shifts[key] = shift
            return shifts[key]

        def book(patient, service, doctor, branch, scheduled, booked_at, status, cashier, coupon=None):
            discount = min(coupon.amount, service.base_price) if coupon else Decimal("0")
            appointment = Appointment.objects.create(
                tenant=tenant, patient=patient, doctor=doctor,
                specialization=service.specialization or random.choice(specializations),
                service=service, scheduled_date=scheduled, status=status, branch=branch,
                price=service.base_price, discount=discount, coupon=coupon,
                created_by=cashier, notes=fake.sentence(),
            )
            # `created_at` is stamped on save; a booking made earlier in a shift
            # has to say so, or the shift's list of bookings would miss it.
            Appointment.all_objects.filter(pk=appointment.pk).update(created_at=booked_at)
            appointment.created_at = booked_at
            return appointment

        def pay(appointment, amount, when, shift):
            amount = Decimal(amount).quantize(cent)
            if amount <= 0:
                return None
            payment = Payment.objects.create(
                tenant=tenant, appointment=appointment, patient=appointment.patient,
                method=random.choice(payment_methods),
                receipt_number="R-" + SerialCounter.next_serial(tenant.id, "receipt", when.date()),
                amount=amount, branch=shift.branch, shift=shift, created_by=shift.user,
            )
            Payment.all_objects.filter(pk=payment.pk).update(date=when)
            return payment

        def spent_coupon(patient, service, used_at, amount):
            return DiscountCoupon.objects.create(
                tenant=tenant, patient=patient, amount=amount, service=service,
                notes="خصم تجريبي", created_by=clinic_admin, used_at=used_at,
            )

        appointments, payments, coupons = [], [], []
        total = spec["appointments"]
        today_pattern = [
            "waiting_paid", "waiting_part", "called_paid", "entered_paid",
            "waiting_paid", "quick_unpaid", "waiting_part",
        ]
        today_count = min(len(today_pattern), max(3, total // 8))
        future_count = total // 6
        past_count = total - today_count - future_count

        # ---- past days: completed and fully paid, or never attended and unpaid
        for i in range(past_count):
            day = today - timedelta(days=random.randint(1, 45))
            branch = random.choice(branches)
            cashier = cashier_for(branch)
            service = random.choice(services)
            patient = random.choice(patients)
            scheduled = at(day, random.randint(9, 17), random.choice([0, 15, 30, 45]))
            booked_at = scheduled - timedelta(minutes=15)
            outcome = random.choices(["completed", "no_show", "cancelled"], weights=[70, 15, 15])[0]
            coupon = None
            if outcome == "completed" and len(coupons) < 3:
                coupon = spent_coupon(
                    patient, service, booked_at, Decimal(random.choice([50, 100, 150])),
                )
                coupons.append(coupon)
            appointment = book(
                patient, service, random.choice(doctors) if doctors else None, branch,
                scheduled, booked_at, outcome, cashier, coupon,
            )
            appointments.append(appointment)
            if outcome == "completed":
                shift = shift_on(branch, day)
                payments.append(pay(appointment, appointment.net_price, booked_at + timedelta(minutes=2), shift))

        # ---- today's queue, all at the first clinic and in reception's open shift
        for i in range(today_count):
            kind = today_pattern[i]
            service = random.choice(services)
            scheduled = now - timedelta(minutes=random.randint(5, 90))
            booked_at = max(scheduled - timedelta(minutes=10), first_booking)
            scheduled = max(scheduled, booked_at)
            shift = shift_on(main, today)
            status = {
                "waiting_paid": "waiting", "waiting_part": "waiting",
                "called_paid": "called", "entered_paid": "waiting", "quick_unpaid": "quick",
            }[kind]
            appointment = book(
                random.choice(patients), service, random.choice(doctors) if doctors else None,
                main, scheduled, booked_at, status, reception,
            )
            if kind == "waiting_part":
                payments.append(pay(appointment, appointment.net_price / 2, booked_at + timedelta(minutes=2), shift))
            elif kind != "quick_unpaid":
                payments.append(pay(appointment, appointment.net_price, booked_at + timedelta(minutes=2), shift))
            if kind == "entered_paid":
                # Paid in full first, then sent in — which opens the visit.
                appointment.status = "entered"
                appointment.save(update_fields=["status"])
            appointments.append(appointment)

        # ---- future bookings: paid in advance, a deposit, or not yet
        for i in range(future_count):
            service = random.choice(services)
            scheduled = at(today + timedelta(days=random.randint(1, 14)), random.randint(9, 17))
            booked_at = max(now - timedelta(minutes=random.randint(5, 150)), first_booking)
            kind = random.choices(["full", "deposit", "none"], weights=[40, 20, 40])[0]
            appointment = book(
                random.choice(patients), service, random.choice(doctors) if doctors else None,
                main, scheduled, booked_at, "waiting" if kind != "none" else "quick", reception,
            )
            appointments.append(appointment)
            if kind != "none":
                amount = appointment.net_price if kind == "full" else appointment.net_price / 3
                payments.append(pay(appointment, amount, booked_at + timedelta(minutes=2), shift_on(main, today)))

        # ---- coupons still to be used, and two that cannot be
        tail = patients[-6:]
        for patient, service, amount in (
            (tail[0], services[0], 100),
            (tail[1], services[-1], 150),
        ):
            coupons.append(DiscountCoupon.objects.create(
                tenant=tenant, patient=patient, amount=Decimal(amount), service=service,
                expires_on=today + timedelta(days=30), notes="كوبون متاح", created_by=clinic_admin,
            ))
        specialty = services[0].specialization or specializations[0]
        coupons.append(DiscountCoupon.objects.create(
            tenant=tenant, patient=tail[2], amount=Decimal("80"), specialization=specialty,
            notes="خصم على التخصص", created_by=clinic_admin,
        ))
        coupons.append(DiscountCoupon.objects.create(
            tenant=tenant, patient=tail[3], amount=Decimal("60"), service=services[0],
            expires_on=today - timedelta(days=5), notes="منتهي", created_by=clinic_admin,
        ))
        coupons.append(DiscountCoupon.objects.create(
            tenant=tenant, patient=tail[4], amount=Decimal("60"), service=services[0],
            voided_at=now - timedelta(days=2), notes="ملغى", created_by=clinic_admin,
        ))

        # ---- expenses, each inside a shift, on that shift's day
        expense_categories = list(ExpenseCategory.objects.filter(tenant=tenant))
        employees = list(Employee.objects.filter(tenant=tenant))
        for (_, branch_pk, day), shift in list(shifts.items()):
            for _ in range(2 if day == today else random.choice([0, 1, 1, 2])):
                Expense.objects.create(
                    tenant=tenant, branch=shift.branch, category=random.choice(expense_categories),
                    employee=random.choice(employees), amount=Decimal(random.randint(50, 900)),
                    date=day, method=random.choice(payment_methods), shift=shift,
                    created_by=shift.user, notes=fake.sentence(),
                )

        # ---- closed shifts carry the summary frozen at closing, as they would
        for shift in shifts.values():
            shift.refresh_from_db()
            if shift.status == CashShift.Status.CLOSED:
                shift.closing_summary = summarize(shift)
                shift.save(update_fields=["closing_summary"])

        return appointments, [p for p in payments if p], coupons, list(shifts.values())

    def _user(self, tenant, email, username, role, branch):
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "username": username,
                "tenant": tenant,
                "role": role,
                "branch": branch,
                "clinic_code": tenant.slug.upper()[:20],
            },
        )
        if created:
            user.set_password(self.password)
            user.save(update_fields=["password"])
            self.created_accounts.append(email)
        elif self.reset_passwords:
            user.set_password(self.password)
            user.save(update_fields=["password"])
            self.created_accounts.append(email)
        return user

    # ----------------------------------------------------------------- report

    def _report(self, summaries):
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Demo data ready."))
        for s in summaries:
            self.stdout.write("")
            self.stdout.write(self.style.MIGRATE_HEADING(f"  {s['tenant'].name}  ({s['slug']})"))
            self.stdout.write(
                f"    {s['branches']} branches  {s['employees']} employees  {s['patients']} patients"
            )
            self.stdout.write(
                f"    {s['services']} services  {s['appointments']} appointments  "
                f"{s['payments']} payments  {s['expenses']} expenses"
            )
            self.stdout.write(
                f"    {s['shifts']} cash shifts (reception's is open today)  "
                f"{s['coupons']} discount coupons"
            )
            self.stdout.write(
                f"    {s['visits']} clinical visits  {s['prescriptions']} prescriptions  "
                f"{s['allergies']} recorded allergies"
            )
            self.stdout.write(
                f"    {s['plans']} treatment plans  {s['sessions']} sessions  "
                f"{s['procedures']} procedures  {s['lab_results']} lab results"
            )
            self.stdout.write(f"    admin@{s['slug']}.local        (Owner — every clinic)")
            self.stdout.write(f"    clinicadmin@{s['slug']}.local  (Admin — first clinic)")
            self.stdout.write(f"    reception@{s['slug']}.local    (Reception)")
            self.stdout.write(f"    doctor@{s['slug']}.local       (Doctor)")
            for account in s["portal"]:
                self.stdout.write(
                    f"    portal /app/portal/{s['slug']}/  phone {account['phone']}  "
                    f"({account['name']})"
                )

        self.stdout.write("")
        if self.created_accounts:
            self.stdout.write(
                f"  Password for the {len(self.created_accounts)} account(s) created "
                f"by this run: {self.password}"
            )
            self.stdout.write("  Shown once and not stored readable. Accounts that already")
            self.stdout.write("  existed keep the password they had.")
        else:
            self.stdout.write("  No accounts were created; existing ones keep their passwords.")
        self.stdout.write("  Log in with the EMAIL, not the username. Portal patients: PHONE.")
        if self.created_portal:
            self.stdout.write(
                f"  {len(self.created_portal)} portal patient login(s) created or reset: same password."
            )
        self.stdout.write(
            self.style.WARNING(
                "  Before real use: python manage.py disable_demo_accounts"
            )
        )
        self.stdout.write("")
        self.stdout.write(
            "  To see isolation working: log in as one clinic, note a patient's URL,"
        )
        self.stdout.write(
            "  then log in as the other and open that same URL — it returns 404."
        )
