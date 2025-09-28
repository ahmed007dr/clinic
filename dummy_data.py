import os
import django
import random
from faker import Faker
from datetime import datetime, timedelta
from decimal import Decimal

# Django setup
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

NUM_EMPLOYEE_TYPES = 3
NUM_SPECIALIZATIONS = 5
NUM_SALARY_TYPES = 2
NUM_EMPLOYEES = 20
NUM_PATIENTS = 50
NUM_APPOINTMENT_STATUSES = 3
NUM_APPOINTMENTS = 100
NUM_PAYMENT_METHODS = 3
NUM_EXPENSE_CATEGORIES = 5
NUM_EXPENSES = 30

print("⏳ Starting fake data generation...")

# ======== Branch ========
branch, created = Branch.objects.get_or_create(
    name="Sohag",
    defaults={
        "code": "BR001",
        "address": fake.address(),
        "phone": fake.phone_number(),
        "email": fake.email(),
        "footer_text": fake.sentence()
    }
)
branches = [branch]
print(f"✅ Created branch: {branch.name}")

# ======== Roles ========
roles = []
for name in ["Admin", "Reception"]:
    role, created = ClinicRole.objects.get_or_create(
        name=name,
        defaults={"description": fake.sentence()}
    )
    roles.append(role)
print(f"✅ Created {len(roles)} roles")

# ======== Users ========
users = []
# Admin user
admin_role = ClinicRole.objects.get(name="Admin")
user_admin, created = User.objects.get_or_create(
    username="dr-ahmed",
    defaults={
        "clinic_code": "CLINIC001",
        "role": admin_role,
        "branch": branch
    }
)
if created:
    user_admin.set_password("123")
    user_admin.save()
users.append(user_admin)

# Reception user
reception_role = ClinicRole.objects.get(name="Reception")
user_reception, created = User.objects.get_or_create(
    username="ahmed2",
    defaults={
        "clinic_code": "CLINIC002",
        "role": reception_role,
        "branch": branch
    }
)
if created:
    user_reception.set_password("123")
    user_reception.save()
users.append(user_reception)
print(f"✅ Created {len(users)} users")

# ======== Employee Types ========
employee_types = []
for name in ["Doctor", "Nurse", "Accountant"]:
    etype, created = EmployeeType.objects.get_or_create(
        name=name,
        defaults={"description": fake.sentence()}
    )
    employee_types.append(etype)
print(f"✅ Created {len(employee_types)} employee types")

# ======== Salary Types ========
salary_types = []
for name in ["Monthly", "Hourly"]:
    stype, created = SalaryType.objects.get_or_create(name=name)
    salary_types.append(stype)
print(f"✅ Created {len(salary_types)} salary types")

# ======== Specializations ========
specializations = []
for _ in range(NUM_SPECIALIZATIONS):
    spec, created = Specialization.objects.get_or_create(
        name=fake.job(),
        defaults={"description": fake.sentence()}
    )
    specializations.append(spec)
print(f"✅ Created {len(specializations)} specializations")

# ======== Services ========
services_data = [
    {"name": "Botox 4000", "base_price": 4000},
    {"name": "Botox 5000", "base_price": 5000},
    {"name": "Botox 8000", "base_price": 8000},
    {"name": "Eximer 120", "base_price": 120},
    {"name": "Eximer 160", "base_price": 160},
    {"name": "Eximer 200", "base_price": 200},
    {"name": "Q switch 800", "base_price": 800},
    {"name": "Q switch 1200", "base_price": 1200},
    {"name": "Q switch 1600", "base_price": 1600},
    {"name": "Co2 500", "base_price": 500},
    {"name": "Co2 750", "base_price": 750},
    {"name": "Co2 1000", "base_price": 1000},
    {"name": "Yellow laser 800", "base_price": 800},
    {"name": "Yellow laser 1200", "base_price": 1200},
    {"name": "Yellow laser 1600", "base_price": 1600},
    {"name": "Yellow laser 2000", "base_price": 2000},
    {"name": "Narrow band", "base_price": 50},
    {"name": "Dermojet", "base_price": 250},
    {"name": "Cryo 250", "base_price": 250},
    {"name": "Cryo 450", "base_price": 450},
    {"name": "Cryo 650", "base_price": 650},
    {"name": "Micro neddling 800", "base_price": 800},
    {"name": "Micro neddling 1200", "base_price": 1200},
    {"name": "Micro neddling 1600", "base_price": 1600},
    {"name": "Micro neddling 2000", "base_price": 2000},
    {"name": "Hi frecator 500", "base_price": 500},
    {"name": "Hi frecator 750", "base_price": 750},
    {"name": "Hi frecator 1000", "base_price": 1000},
]
services = []
for service_data in services_data:
    service, created = Service.objects.get_or_create(
        name=service_data["name"],
        base_price=Decimal(service_data["base_price"]),
        defaults={
            "description": fake.sentence(),
            "specialization": random.choice(specializations)
        }
    )
    services.append(service)
print(f"✅ Created {len(services)} services")

# ======== Employees ========
employees = []
for _ in range(NUM_EMPLOYEES):
    emp = Employee.objects.create(
        name=fake.name(),
        employee_type=random.choice(employee_types),
        branch=branch,
        national_id=fake.unique.numerify(text="###########"),
        phone1=fake.phone_number(),
        email=fake.email(),
        hire_date=fake.date_this_decade(),
        salary_type=random.choice(salary_types),
        salary_value=Decimal(random.randint(3000, 15000))
    )
    emp.specializations.set(random.sample(specializations, k=random.randint(1, 2)))
    employees.append(emp)
print(f"✅ Created {len(employees)} employees")

# ======== Patients ========
patients = []
for _ in range(NUM_PATIENTS):
    patient = Patient.objects.create(
        name=fake.name(),
        national_id=fake.unique.numerify(text="###########"),
        gender=random.choice(["male", "female"]),
        birth_date=fake.date_of_birth(minimum_age=18, maximum_age=80),
        phone1=fake.phone_number(),
        email=fake.email(),
        marital_status=random.choice(["single", "married"]),
        address=fake.address(),
        branch=branch
    )
    patients.append(patient)
print(f"✅ Created {len(patients)} patients")

# ======== Appointment Status ========
statuses = []
for name in ["Scheduled", "Cancelled", "Completed"]:
    status, created = AppointmentStatus.objects.get_or_create(
        name=name,
        defaults={"description": fake.sentence()}
    )
    statuses.append(status)
print(f"✅ Created {len(statuses)} appointment statuses")

# ======== Appointments ========
appointments = []
for _ in range(NUM_APPOINTMENTS):
    appt = Appointment.objects.create(
        patient=random.choice(patients),
        doctor=random.choice([e for e in employees if e.employee_type.name == "Doctor"]),
        specialization=random.choice(specializations),
        service=random.choice(services),
        scheduled_date=fake.date_time_this_year(),
        status=random.choice(statuses),
        branch=branch,
        price=Decimal(random.choice([s.base_price for s in services])),
        created_by=random.choice(users),
        notes=fake.text(max_nb_chars=100)
    )
    appointments.append(appt)
print(f"✅ Created {len(appointments)} appointments")

# ======== Payment Methods ========
payment_methods = []
for name in ["Cash", "Visa", "Insurance"]:
    method, created = PaymentMethod.objects.get_or_create(
        name=name,
        defaults={"description": fake.sentence()}
    )
    payment_methods.append(method)
print(f"✅ Created {len(payment_methods)} payment methods")

# ======== Payments ========
payments = []
for appt in appointments:
    pay = Payment.objects.create(
        appointment=appt,
        patient=appt.patient,
        method=random.choice(payment_methods),
        receipt_number=fake.unique.bothify(text="RCPT#####"),
        amount=appt.price,
        branch=branch,
        notes=fake.sentence()
    )
    payments.append(pay)
print(f"✅ Created {len(payments)} payments")

# ======== Expense Categories ========
expense_categories = []
for _ in range(NUM_EXPENSE_CATEGORIES):
    cat, created = ExpenseCategory.objects.get_or_create(
        name=fake.word(),
        defaults={"description": fake.sentence()}
    )
    expense_categories.append(cat)
print(f"✅ Created {len(expense_categories)} expense categories")

# ======== Expenses ========
expenses = []
for _ in range(NUM_EXPENSES):
    expense = Expense.objects.create(
        branch=branch,
        category=random.choice(expense_categories),
        employee=random.choice(employees),
        amount=Decimal(random.randint(100, 5000)),
        date=fake.date_this_year(),
        created_by=random.choice(users),
        notes=fake.sentence()
    )
    expenses.append(expense)
print(f"✅ Created {len(expenses)} expenses")

# ========================
# Summary
# ========================
print("\n🎉 Fake data generation completed successfully!")
print(f" Branches: 1 (Sohag)")
print(f" Users: 2 (dr-ahmed, ahmed2)")
print(f" Employees: {len(employees)}")
print(f" Patients: {len(patients)}")
print(f" Services: {len(services)}")
print(f" Appointments: {len(appointments)}")
print(f" Payments: {len(payments)}")
print(f" Expenses: {len(expenses)}")