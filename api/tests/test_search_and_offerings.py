"""Search-first lists (patients, expenses, staff) and a doctor's bookable offer.

The screens hold every list back until "بحث" is pressed; what they then ask
the server for is tested here: the filters behind each criterion, and the
`doctors/offerings` endpoint the booking form uses to show a doctor's
contracted services with their prices.
"""

from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import ClinicRole
from billing.models import DoctorServiceRate, Expense
from branches.models import Branch
from employees.models import Employee, EmployeeType, Specialization
from patients.models import Patient
from services.models import Service
from tenants.context import tenant_context
from tenants.models import Tenant

User = get_user_model()


class SearchFilterTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        with tenant_context(self.tenant):
            self.a = Branch.all_objects.create(tenant=self.tenant, name="A-Sr", code="AS")
            self.b = Branch.all_objects.create(tenant=self.tenant, name="B-Sr", code="BS")
            owner_role = ClinicRole.all_objects.get_or_create(tenant=self.tenant, name="Owner")[0]
            self.doctor_type = EmployeeType.all_objects.get_or_create(tenant=self.tenant, name="Doctor")[0]
            self.nurse_type = EmployeeType.all_objects.get_or_create(tenant=self.tenant, name="Nurse")[0]
            self.owner = User.objects.create_user(
                username="own", email="own@sr.local", password="pass12345",
                tenant=self.tenant, role=owner_role, branch=self.a,
            )

            def patient(name, gender, branch, phone):
                return Patient.all_objects.create(
                    tenant=self.tenant, name=name, gender=gender, branch=branch, phone1=phone,
                )

            self.male_a = patient("Adam", "male", self.a, "0100000001")
            self.female_a = patient("Eve", "female", self.a, "0100000002")
            self.female_b = patient("Hana", "female", self.b, "0100000003")
            # Registered on known days, so the date range can be checked.
            Patient.all_objects.filter(pk=self.male_a.pk).update(created_at=datetime(2026, 1, 10, 9))
            Patient.all_objects.filter(pk=self.female_a.pk).update(created_at=datetime(2026, 2, 10, 9))
            Patient.all_objects.filter(pk=self.female_b.pk).update(created_at=datetime(2026, 3, 10, 9))

            def staff(name, kind, branch, nid, phone2=""):
                return Employee.all_objects.create(
                    tenant=self.tenant, name=name, branch=branch, employee_type=kind,
                    national_id=nid, salary_value=0, phone2=phone2,
                )

            self.dr = staff("Dr Sr", self.doctor_type, self.a, "SR-1", phone2="0122222222")
            self.nurse = staff("Nurse Sr", self.nurse_type, self.b, "SR-2")

            def expense(amount, when, branch, employee=None):
                return Expense.all_objects.create(
                    tenant=self.tenant, amount=amount, date=when, branch=branch, employee=employee,
                )

            self.small = expense(50, date(2026, 5, 1), self.a)
            self.medium = expense(200, date(2026, 5, 10), self.a, employee=self.dr)
            self.large = expense(900, date(2026, 6, 1), self.b, employee=self.nurse)
        self.assertTrue(self.client.login(email="own@sr.local", password="pass12345"))

    def names(self, url_name, **params):
        response = self.client.get(reverse(url_name), params)
        self.assertEqual(response.status_code, 200, response.content)
        return {row.get("name") or row.get("amount") for row in response.json()["results"]}

    # ------------------------------------------------------------- patients

    def test_patients_by_gender_registration_date_and_branch(self):
        self.assertEqual(self.names("api:patient-list", gender="male"), {"Adam"})
        self.assertEqual(self.names("api:patient-list", gender="female"), {"Eve", "Hana"})
        self.assertEqual(
            self.names("api:patient-list", created_from="2026-02-01", created_to="2026-02-28"), {"Eve"}
        )
        self.assertEqual(self.names("api:patient-list", created_from="2026-02-01"), {"Eve", "Hana"})
        self.assertEqual(self.names("api:patient-list", branch=str(self.b.uuid)), {"Hana"})
        self.assertEqual(
            self.names("api:patient-list", gender="female", branch=str(self.a.uuid)), {"Eve"}
        )

    def test_patients_by_name_or_phone(self):
        self.assertEqual(self.names("api:patient-list", search="Adam"), {"Adam"})
        self.assertEqual(self.names("api:patient-list", search="0100000003"), {"Hana"})

    # ------------------------------------------------------------- expenses

    def test_expenses_by_amount_range_employee_and_branch(self):
        amounts = lambda **p: {Decimal(a) for a in self.names("api:expense-list", **p)}  # noqa: E731
        self.assertEqual(amounts(amount_min="100"), {Decimal("200"), Decimal("900")})
        self.assertEqual(amounts(amount_max="200"), {Decimal("50"), Decimal("200")})
        self.assertEqual(amounts(amount_min="100", amount_max="500"), {Decimal("200")})
        self.assertEqual(amounts(employee=str(self.dr.uuid)), {Decimal("200")})
        self.assertEqual(amounts(branch=str(self.b.uuid)), {Decimal("900")})
        self.assertEqual(amounts(**{"from": "2026-05-05", "to": "2026-05-31"}), {Decimal("200")})

    def test_a_malformed_amount_is_refused_not_ignored(self):
        response = self.client.get(reverse("api:expense-list"), {"amount_min": "abc"})
        self.assertEqual(response.status_code, 400)

    # ---------------------------------------------------------------- staff

    def test_staff_by_job_branch_and_either_phone(self):
        self.assertEqual(self.names("api:employee-list", employee_type=str(self.doctor_type.uuid)), {"Dr Sr"})
        self.assertEqual(self.names("api:employee-list", branch=str(self.b.uuid)), {"Nurse Sr"})
        self.assertEqual(self.names("api:employee-list", search="0122222222"), {"Dr Sr"})


class OfferingsTests(TestCase):
    """What the booking form shows once a doctor is chosen."""

    def setUp(self):
        self.tenant = Tenant.objects.first()
        with tenant_context(self.tenant):
            self.branch = Branch.all_objects.create(tenant=self.tenant, name="Of", code="OF")
            self.far = Branch.all_objects.create(tenant=self.tenant, name="Far-Of", code="FO")
            roles = {
                n: ClinicRole.all_objects.get_or_create(tenant=self.tenant, name=n)[0]
                for n in ("Reception",)
            }
            doctor_type = EmployeeType.all_objects.get_or_create(tenant=self.tenant, name="Doctor")[0]
            self.derma = Specialization.all_objects.create(tenant=self.tenant, name="Derma-Of")
            self.laser_spec = Specialization.all_objects.create(tenant=self.tenant, name="Laser-Of")
            self.other_spec = Specialization.all_objects.create(tenant=self.tenant, name="Other-Of")

            def doctor(name, nid, branch):
                return Employee.all_objects.create(
                    tenant=self.tenant, name=name, branch=branch, employee_type=doctor_type,
                    national_id=nid, salary_value=0,
                )

            self.dr = doctor("Dr Of", "OF-1", self.branch)
            self.dr.specializations.set([self.derma, self.laser_spec])
            self.dr_far = doctor("Dr Far", "OF-2", self.far)
            self.consult = Service.all_objects.create(
                tenant=self.tenant, name="Consult-Of", base_price=300, specialization=self.derma
            )
            self.laser = Service.all_objects.create(
                tenant=self.tenant, name="Laser-Of", base_price=1000, specialization=self.laser_spec
            )
            self.peel = Service.all_objects.create(tenant=self.tenant, name="Peel-Of", base_price=500)
            self.stopped = Service.all_objects.create(
                tenant=self.tenant, name="Stopped-Of", base_price=10, is_active=False
            )
            # Contracted: consult at the catalogue price, laser at a contract
            # price with a share; peel is NOT contracted; the stopped service
            # has a line but is off; a line switched off is not offered.
            DoctorServiceRate.all_objects.create(tenant=self.tenant, doctor=self.dr, service=self.consult)
            DoctorServiceRate.all_objects.create(
                tenant=self.tenant, doctor=self.dr, service=self.laser,
                price=Decimal("800.00"), commission_percent=Decimal("45"),
            )
            DoctorServiceRate.all_objects.create(tenant=self.tenant, doctor=self.dr, service=self.stopped)
            DoctorServiceRate.all_objects.create(
                tenant=self.tenant, doctor=self.dr, service=self.peel, is_active=False
            )
            User.objects.create_user(
                username="deskof", email="deskof@of.local", password="pass12345",
                tenant=self.tenant, role=roles["Reception"], branch=self.branch,
            )
        self.assertTrue(self.client.login(email="deskof@of.local", password="pass12345"))

    def offer(self, **params):
        return self.client.get(reverse("api:doctor-offerings"), params)

    def test_a_doctor_offers_only_contracted_services_at_their_prices(self):
        response = self.offer(doctor=str(self.dr.uuid))
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertTrue(body["contracted"])
        prices = {row["name"]: row["price"] for row in body["services"]}
        # Contract price where there is one, else the catalogue price; not the
        # uncontracted, switched-off or stopped services.
        self.assertEqual(prices, {"Consult-Of": "300.00", "Laser-Of": "800.00"})
        laser = next(row for row in body["services"] if row["name"] == "Laser-Of")
        self.assertEqual(laser["specialization"], str(self.laser_spec.uuid))

    def test_a_doctor_offers_only_their_own_specialties(self):
        names = {row["name"] for row in self.offer(doctor=str(self.dr.uuid)).json()["specializations"]}
        self.assertEqual(names, {"Derma-Of", "Laser-Of"})

    def test_the_doctors_share_is_never_sent_to_the_front_desk(self):
        text = self.offer(doctor=str(self.dr.uuid)).content.decode()
        self.assertNotIn("commission", text)
        self.assertNotIn("percent", text)

    def test_a_doctor_with_no_contract_offers_nothing(self):
        with tenant_context(self.tenant):
            bare = Employee.all_objects.create(
                tenant=self.tenant, name="Dr Bare", branch=self.branch,
                employee_type=self.dr.employee_type, national_id="OF-3", salary_value=0,
            )
        body = self.offer(doctor=str(bare.uuid)).json()
        self.assertTrue(body["contracted"])
        self.assertEqual(body["services"], [])

    def test_without_a_doctor_the_whole_catalogue_is_offered(self):
        body = self.offer().json()
        self.assertFalse(body["contracted"])
        names = {row["name"] for row in body["services"]}
        self.assertEqual(names, {"Consult-Of", "Laser-Of", "Peel-Of"})
        self.assertIn("Other-Of", {row["name"] for row in body["specializations"]})

    def test_a_doctor_this_user_cannot_book_is_a_404(self):
        self.assertEqual(self.offer(doctor=str(self.dr_far.uuid)).status_code, 404)
