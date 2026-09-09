"""DATA-001 — column widths that survive real data.

`varchar(20)` is advisory in SQLite and enforced in PostgreSQL, so the phone
columns held over-length values locally that would have raised `DataError` on
import. The audit found 9 such rows. Widening the columns removes the class of
failure rather than truncating the data, which for a phone number means a
contact that cannot be dialled.

The round-trip test below is the one that matters: before the widening it
passed on SQLite and failed on PostgreSQL, which is exactly the shape of bug
that reaches production unnoticed.
"""

from django.apps import apps
from django.db import models
from django.test import TestCase

from branches.models import Branch
from employees.models import Employee, EmployeeType
from patients.models import Patient

from .context import tenant_context
from .models import Tenant

# Enough for an international number with an extension, or two local numbers in
# one field, which is how clinic staff actually use these.
MINIMUM_PHONE_WIDTH = 32

# 30 characters: a realistic worst case, comfortably over the old limit of 20.
LONG_PHONE = "+20 100 123 4567 x1234 / 0100"


class PhoneColumnWidthTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()

    def test_every_phone_column_is_wide_enough(self):
        """Stated as a rule over the model registry, so a phone field added to a
        new model at the old width fails here rather than at import time."""
        found = 0
        for model in apps.get_models():
            if model._meta.proxy or not model._meta.managed:
                continue
            for field in model._meta.local_fields:
                if not isinstance(field, models.CharField):
                    continue
                if "phone" not in field.name and "mobile" not in field.name:
                    continue
                found += 1
                with self.subTest(field=f"{model._meta.label}.{field.name}"):
                    self.assertGreaterEqual(
                        field.max_length, MINIMUM_PHONE_WIDTH,
                        f"{model._meta.label}.{field.name} is "
                        f"max_length={field.max_length}; an international number "
                        f"with an extension does not fit",
                    )
        self.assertGreaterEqual(found, 5, "expected at least 5 phone columns")

    def test_a_long_phone_number_round_trips(self):
        """The regression proper. On PostgreSQL this raised DataError before the
        columns were widened; on SQLite it silently passed, which is why the
        problem survived to be found by the migration audit."""
        self.assertGreater(len(LONG_PHONE), 20, "the fixture must exceed the old limit")

        with tenant_context(self.tenant):
            branch = Branch.all_objects.create(
                tenant=self.tenant, name="Wide", code="WIDE", phone=LONG_PHONE,
            )
            patient = Patient.all_objects.create(
                tenant=self.tenant, name="Long Phone", branch=branch,
                phone1=LONG_PHONE, phone2=LONG_PHONE,
            )
            employee_type = EmployeeType.all_objects.create(
                tenant=self.tenant, name="Reception Staff",
            )
            employee = Employee.all_objects.create(
                tenant=self.tenant, name="Long Phone Staff", branch=branch,
                employee_type=employee_type, national_id="X-1", salary_value=1000,
                phone1=LONG_PHONE, phone2=LONG_PHONE,
            )

            for obj, field in (
                (branch, "phone"),
                (patient, "phone1"), (patient, "phone2"),
                (employee, "phone1"), (employee, "phone2"),
            ):
                obj.refresh_from_db()
                with self.subTest(field=f"{type(obj).__name__}.{field}"):
                    # Stored whole, not silently truncated by the database.
                    self.assertEqual(getattr(obj, field), LONG_PHONE)

    def test_the_seeder_stays_within_the_column(self):
        """The seeder truncates Faker output explicitly. If that bound and the
        column ever disagree again, PostgreSQL — not the test suite — is what
        reports it, so pin them together."""
        from pathlib import Path

        source = Path("tenants/management/commands/seed_demo.py").read_text(encoding="utf-8")
        self.assertNotIn(
            "phone_number()[:20]", source,
            "the seeder still truncates to the old column width",
        )
        self.assertIn(f"phone_number()[:{MINIMUM_PHONE_WIDTH}]", source)
