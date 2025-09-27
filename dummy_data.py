import os
import django
import random
from faker import Faker
from datetime import datetime, timedelta

# إعداد Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")
django.setup()

from accounts.models import User, ClinicRole
from branches.models import Branch
from employees.models import Employee, EmployeeType, Specialization, SalaryType
from patients.models import Patient
from services.models import Service
from appointments.models import AppointmentStatus, Appointment
from billing.models import PaymentMethod, Payment, ExpenseCategory, Expense

fake = Faker("ar_EG")

NUM_BRANCHES = 3
NUM_ROLES = 3
NUM_EMPLOYEE_TYPES = 3
NUM_SPECIALIZATIONS = 5
NUM_SALARY_TYPES = 2
NUM_EMPLOYEES = 20
NUM_PATIENTS = 50
NUM_SERVICES = 10
NUM_APPOINTMENT_STATUSES = 3
NUM_APPOINTMENTS = 100
NUM_PAYMENT_METHODS = 3
NUM_EXPENSE_CATEGORIES = 5
NUM_EXPENSES = 30

print("⏳ بدء إنشاء البيانات الوهمية...")

# --- Branches ---
# ======== Roles ========
roles = []
for name in ["Admin", "Reception", "Doctor"]:
    role, created = ClinicRole.objects.get_or_create(
        name=name,
        defaults={"description": fake.sentence()}
    )
    roles.append(role)
print(f"✅ تم إنشاء أو استدعاء {len(roles)} أدوار")

# ======== Employee Types ========
employee_types = []
for name in ["Doctor", "Nurse", "Accountant"]:
    etype, created = EmployeeType.objects.get_or_create(
        name=name,
        defaults={"description": fake.sentence()}
    )
    employee_types.append(etype)
print(f"✅ تم إنشاء أو استدعاء {len(employee_types)} أنواع موظفين")

# ======== Salary Types ========
salary_types = []
for name in ["Monthly", "Hourly"]:
    stype, created = SalaryType.objects.get_or_create(name=name)
    salary_types.append(stype)
print(f"✅ تم إنشاء أو استدعاء {len(salary_types)} أنواع رواتب")

# ======== Appointment Status ========
statuses = []
for name in ["Scheduled", "Cancelled", "Completed"]:
    status, created = AppointmentStatus.objects.get_or_create(
        name=name,
        defaults={"description": fake.sentence()}
    )
    statuses.append(status)
print(f"✅ تم إنشاء أو استدعاء {len(statuses)} حالات مواعيد")

# ======== Payment Methods ========
payment_methods = []
for name in ["Cash", "Visa", "Insurance"]:
    method, created = PaymentMethod.objects.get_or_create(
        name=name,
        defaults={"description": fake.sentence()}
    )
    payment_methods.append(method)
print(f"✅ تم إنشاء أو استدعاء {len(payment_methods)} طرق دفع")

# ======== Branches ========
branches = []
for _ in range(3):
    branch = Branch.objects.create(
        name=fake.company(),
        code=fake.unique.bothify(text="BR###"),
        address=fake.address(),
        phone=fake.phone_number(),
        email=fake.email(),
        footer_text=fake.sentence()
    )
    branches.append(branch)
print(f"✅ تم إنشاء {len(branches)} فروع")

# ======== Specializations ========
specializations = []
for _ in range(5):
    spec, created = Specialization.objects.get_or_create(
        name=fake.job(),
        defaults={"description": fake.sentence()}
    )
    specializations.append(spec)
print(f"✅ تم إنشاء أو استدعاء {len(specializations)} تخصصات")

# ======== Employees ========
employees = []
for _ in range(10):
    emp = Employee.objects.create(
        name=fake.name(),
        employee_type=random.choice(employee_types),
        branch=random.choice(branches),
        national_id=fake.unique.numerify(text="###########"),
        phone1=fake.phone_number(),
        email=fake.email(),
        hire_date=fake.date_this_decade(),
        salary_type=random.choice(salary_types),
        salary_value=random.randint(3000, 15000)
    )
    emp.specializations.set(random.sample(specializations, k=random.randint(1, 2)))
    employees.append(emp)
print(f"✅ تم إنشاء {len(employees)} موظفين")

# ======== Users ========
users = []
for role in roles:
    user = User.objects.create_user(
        username=fake.unique.user_name(),
        password="123456",
        clinic_code=fake.bothify(text="CLINIC###"),
        role=role,
        branch=random.choice(branches)
    )
    users.append(user)
print(f"✅ تم إنشاء {len(users)} مستخدمين")

# ======== Patients ========
patients = []
for _ in range(20):
    patient = Patient.objects.create(
        name=fake.name(),
        national_id=fake.unique.numerify(text="###########"),
        gender=random.choice(["male", "female"]),
        birth_date=fake.date_of_birth(),
        phone1=fake.phone_number(),
        email=fake.email(),
        marital_status=random.choice(["single", "married"]),
        address=fake.address(),
        branch=random.choice(branches)
    )
    patients.append(patient)
print(f"✅ تم إنشاء {len(patients)} مرضى")

# ======== Services ========
services = []
for _ in range(10):
    service = Service.objects.create(
        name=fake.bs(),
        description=fake.sentence(),
        specialization=random.choice(specializations),
        base_price=random.randint(200, 2000)
    )
    services.append(service)
print(f"✅ تم إنشاء {len(services)} خدمات")

# ======== Appointments ========
appointments = []
for _ in range(30):
    appt = Appointment.objects.create(
        patient=random.choice(patients),
        doctor=random.choice([e for e in employees if e.employee_type.name == "Doctor"]),
        specialization=random.choice(specializations),
        service=random.choice(services),
        scheduled_date=fake.date_time_this_year(),
        status=random.choice(statuses),
        branch=random.choice(branches),
        price=random.randint(200, 2000),
        created_by=random.choice(users),
        notes=fake.text()
    )
    appointments.append(appt)
print(f"✅ تم إنشاء {len(appointments)} مواعيد")

# ======== Payments ========
payments = []
for appt in appointments:
    pay = Payment.objects.create(
        appointment=appt,
        patient=appt.patient,
        method=random.choice(payment_methods),
        receipt_number=fake.unique.bothify(text="RCPT#####"),
        amount=appt.price,
        branch=appt.branch,
        notes=fake.sentence()
    )
    payments.append(pay)
print(f"✅ تم إنشاء {len(payments)} دفعات")

# ======== Expense Categories ========
expense_categories = []
for _ in range(5):
    cat, created = ExpenseCategory.objects.get_or_create(
        name=fake.word(),
        defaults={"description": fake.sentence()}
    )
    expense_categories.append(cat)
print(f"✅ تم إنشاء أو استدعاء {len(expense_categories)} فئات مصروفات")

# ======== Expenses ========
expenses = []
for _ in range(20):
    expense = Expense.objects.create(
        branch=random.choice(branches),
        category=random.choice(expense_categories),
        employee=random.choice(employees),
        amount=random.randint(100, 5000),
        date=fake.date_this_year(),
        created_by=random.choice(users),
        notes=fake.sentence()
    )
    expenses.append(expense)
print(f"✅ تم إنشاء {len(expenses)} مصروفات")

print("🎉 تم إنشاء كل البيانات الوهمية بنجاح!")
