"""Demo data for local development and manual testing.

Seeds two tenants on purpose. A single tenant proves nothing about isolation —
with two, you can log in as one clinic and confirm the other's patients,
services and revenue are genuinely unreachable.

    python manage.py seed_demo
    python manage.py seed_demo --reset     # wipe demo data first
"""

import random
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import ClinicRole
from appointments.models import Appointment
from audit.models import AuditLog
from billing.models import Expense, ExpenseCategory, Payment, PaymentMethod
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
from services.models import Service
from tenants.context import tenant_context
from tenants.models import SerialCounter, Tenant
from tenants.provisioning import provision_tenant_defaults

User = get_user_model()

DEMO_PASSWORD = "demo-clinic-2026"

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

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing demo data before seeding.",
        )

    def handle(self, *args, **options):
        try:
            from faker import Faker
        except ImportError:
            self.stderr.write("Faker is required: pip install -r requirements.txt")
            return

        self.fake = Faker("ar_EG")
        random.seed(20260908)  # reproducible runs

        if options["reset"]:
            self._reset()

        summaries = []
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
        # Clinical records first: Visit.patient, Allergy.patient,
        # TreatmentPlan.patient, TreatmentSession.patient and
        # Procedure.patient/.visit and LabResult.patient are all PROTECT, so
        # patients and visits
        # cannot be cleared while any of these exist. Sessions before plans,
        # and procedures before visits, for the same reason.
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

    # ------------------------------------------------------------------- seed

    def _seed_tenant(self, spec):
        fake = self.fake

        tenant, created = Tenant.objects.get_or_create(
            slug=spec["slug"],
            defaults={"name": spec["name"], "status": Tenant.Status.ACTIVE},
        )
        provision_tenant_defaults(tenant)

        # Inside this block, plain .objects queries are scoped to this tenant.
        with tenant_context(tenant):
            branches = [
                Branch.objects.get_or_create(
                    tenant=tenant, code=code,
                    defaults={"name": name, "address": fake.address(), "phone": fake.phone_number()[:32]},
                )[0]
                for name, code in spec["branches"]
            ]

            admin_role = ClinicRole.objects.get(name="Admin")
            reception_role = ClinicRole.objects.get(name="Reception")
            doctor_role = ClinicRole.objects.get(name="Doctor")
            doctor_type = EmployeeType.objects.get(name="Doctor")
            nurse_type = EmployeeType.objects.get_or_create(
                tenant=tenant, name="Nurse", defaults={"description": "Nursing staff"}
            )[0]

            users = [
                self._user(tenant, f"admin@{spec['slug']}.local", "admin", admin_role, branches[0]),
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

            appointments, payments = [], []
            for i in range(spec["appointments"]):
                service = random.choice(services)
                # A tenth land today so the waiting list and dashboard aren't empty.
                if random.random() < 0.1:
                    scheduled = timezone.now()
                else:
                    scheduled = fake.date_time_between(start_date="-60d", end_date="+14d")
                    # The project runs USE_TZ=False; stay naive unless that changes.
                    if settings.USE_TZ:
                        scheduled = timezone.make_aware(scheduled)
                appointment = Appointment.objects.create(
                    tenant=tenant,
                    patient=random.choice(patients),
                    doctor=random.choice(doctors) if doctors else None,
                    specialization=random.choice(specializations),
                    service=service,
                    scheduled_date=scheduled,
                    status=random.choice(["entered", "waiting", "called", "quick"]),
                    branch=random.choice(branches),
                    price=service.base_price,
                    created_by=random.choice(users),
                    notes=fake.sentence(),
                )
                appointments.append(appointment)

                if random.random() < 0.8:
                    payments.append(
                        Payment.objects.create(
                            tenant=tenant,
                            appointment=appointment,
                            patient=appointment.patient,
                            method=random.choice(payment_methods),
                            receipt_number=f"{spec['slug'][:3].upper()}-{i + 1:05d}",
                            amount=appointment.price,
                            branch=appointment.branch,
                            notes=fake.sentence(),
                        )
                    )

            # Clinical records for roughly a third of the visits that happened.
            visits = []
            for appointment in appointments[: max(3, len(appointments) // 3)]:
                visits.append(
                    Visit.objects.create(
                        tenant=tenant,
                        patient=appointment.patient,
                        appointment=appointment,
                        doctor=appointment.doctor,
                        branch=appointment.branch,
                        visit_date=appointment.scheduled_date,
                        chief_complaint=random.choice(COMPLAINTS),
                        examination=fake.sentence(),
                        diagnosis=random.choice(DIAGNOSES),
                        treatment_plan=fake.sentence(),
                        created_by=users[2],
                    )
                )

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

            expenses = [
                Expense.objects.create(
                    tenant=tenant,
                    branch=random.choice(branches),
                    category=random.choice(expense_categories),
                    employee=random.choice(employees),
                    amount=Decimal(random.randint(200, 6000)),
                    date=fake.date_between(start_date="-60d", end_date="today"),
                    created_by=random.choice(users),
                    notes=fake.sentence(),
                )
                for _ in range(spec["appointments"] // 3)
            ]

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
            "visits": len(visits),
            "allergies": len(allergies),
            "prescriptions": len(prescriptions),
            "plans": len(plans),
            "sessions": len(sessions),
            "procedures": len(procedures),
            "lab_results": len(lab_results),
        }

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
            user.set_password(DEMO_PASSWORD)
            user.save(update_fields=["password"])
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
                f"    {s['visits']} clinical visits  {s['prescriptions']} prescriptions  "
                f"{s['allergies']} recorded allergies"
            )
            self.stdout.write(
                f"    {s['plans']} treatment plans  {s['sessions']} sessions  "
                f"{s['procedures']} procedures  {s['lab_results']} lab results"
            )
            self.stdout.write(f"    admin@{s['slug']}.local      (Admin)")
            self.stdout.write(f"    reception@{s['slug']}.local  (Reception)")
            self.stdout.write(f"    doctor@{s['slug']}.local     (Doctor)")

        self.stdout.write("")
        self.stdout.write(f"  Password for every demo account: {DEMO_PASSWORD}")
        self.stdout.write("  Log in with the EMAIL, not the username.")
        self.stdout.write("")
        self.stdout.write(
            "  To see isolation working: log in as one clinic, note a patient's URL,"
        )
        self.stdout.write(
            "  then log in as the other and open that same URL — it returns 404."
        )
