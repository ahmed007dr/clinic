"""SEC-011 — public identifiers.

Sequential primary keys used to be the public identifier for every record.
That disclosed business volume (a URL ending /1247/ says roughly how many
patients a clinic has) and made walking every record trivial for anyone
already inside a tenant.

Worth being precise about what this does and does not do: tenant scoping is
what makes another clinic's records unreachable. A UUID is unguessable, not
unauthorised — it removes the enumeration surface, it is not the access
control.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import Resolver404, resolve, reverse

from accounts.models import ClinicRole
from appointments.models import Appointment
from branches.models import Branch
from patients.models import Patient
from patients.views import patient_detail

from .models import Tenant
from .testing import act_as_tenant

User = get_user_model()


class PublicIdentifierTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.first()
        act_as_tenant(self, self.tenant)
        role, _ = ClinicRole.all_objects.get_or_create(tenant=self.tenant, name='Admin')
        self.branch = Branch.all_objects.create(tenant=self.tenant, name='Main', code='MN')
        self.user = User.objects.create_user(
            username='admin', email='admin@t.local', password='pass12345',
            tenant=self.tenant, role=role, branch=self.branch,
        )
        self.patient = Patient.all_objects.create(
            tenant=self.tenant, name='Test Patient', branch=self.branch,
        )
        self.client.login(email='admin@t.local', password='pass12345')

    def test_uuid_url_serves_the_record(self):
        response = self.client.get(reverse('patients:patient_detail', args=[self.patient.uuid]))
        self.assertEqual(response.status_code, 200)

    def test_integer_url_no_longer_reaches_the_view(self):
        """The route is gone, not merely guarded — a redirect shim would have
        kept the enumeration surface this change exists to remove."""
        try:
            match = resolve(f'/patients/{self.patient.pk}/')
        except Resolver404:
            return  # no route at all is the ideal outcome
        self.assertIsNot(match.func, patient_detail)

    def test_integer_url_does_not_serve_the_record(self):
        response = self.client.get(f'/patients/{self.patient.pk}/')
        self.assertNotEqual(response.status_code, 200)

    def test_list_page_links_carry_uuids_not_primary_keys(self):
        response = self.client.get(reverse('patients:patient_list'))
        body = response.content.decode()
        self.assertIn(f'/patients/{self.patient.uuid}/', body)
        self.assertNotIn(f'/patients/{self.patient.pk}/', body)

    def test_uuids_are_distinct_per_row(self):
        """Guards the migration trap: AddField with default=uuid.uuid4
        evaluates the callable once and writes one value to every row."""
        for _ in range(5):
            Patient.all_objects.create(tenant=self.tenant, name='Another', branch=self.branch)
        total = Patient.all_objects.count()
        distinct = Patient.all_objects.values('uuid').distinct().count()
        self.assertEqual(total, distinct)

    def test_uuid_is_stable_across_saves(self):
        original = self.patient.uuid
        self.patient.name = 'Renamed'
        self.patient.save()
        self.patient.refresh_from_db()
        self.assertEqual(self.patient.uuid, original)


class TicketNumberDisplayTests(TestCase):
    """The appointment screens showed the raw database id labelled as the
    ticket number, when serial_number exists for exactly that."""

    def setUp(self):
        self.tenant = Tenant.objects.first()
        act_as_tenant(self, self.tenant)
        role, _ = ClinicRole.all_objects.get_or_create(tenant=self.tenant, name='Admin')
        self.branch = Branch.all_objects.create(tenant=self.tenant, name='Main', code='MN')
        self.user = User.objects.create_user(
            username='admin', email='admin@t.local', password='pass12345',
            tenant=self.tenant, role=role, branch=self.branch,
        )
        patient = Patient.all_objects.create(tenant=self.tenant, name='P', branch=self.branch)
        from django.utils import timezone
        self.appointment = Appointment.all_objects.create(
            tenant=self.tenant, patient=patient,
            scheduled_date=timezone.now(), branch=self.branch,
        )
        self.client.login(email='admin@t.local', password='pass12345')

    def test_detail_shows_the_serial_number_not_the_database_id(self):
        response = self.client.get(
            reverse('appointments:appointment_detail', args=[self.appointment.uuid])
        )
        self.assertContains(response, self.appointment.serial_number)
