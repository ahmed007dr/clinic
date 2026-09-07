from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from accounts.models import ClinicRole
from branches.models import Branch

User = get_user_model()


class ServiceAuthorizationTests(TestCase):
    """Regression tests for BE-002: service management must use the same
    role-based authorization as every other app, not is_superuser."""

    def setUp(self):
        self.branch = Branch.objects.create(name='Branch A', code='A')
        self.admin_role, _ = ClinicRole.objects.get_or_create(name='Admin')
        self.reception_role, _ = ClinicRole.objects.get_or_create(name='Reception')

        # role='Admin' but NOT a Django is_superuser — this is the case that
        # was broken before BE-002 (previously blocked by the is_superuser check).
        self.branch_admin = User.objects.create_user(username='admin', password='pass12345', role=self.admin_role, branch=self.branch)
        self.reception = User.objects.create_user(username='rec', password='pass12345', role=self.reception_role, branch=self.branch)

    def test_role_admin_without_superuser_can_create_service(self):
        self.client.login(username='admin', password='pass12345')
        response = self.client.get(reverse('services:service_create'))
        self.assertEqual(response.status_code, 200)

    def test_reception_cannot_create_service(self):
        self.client.login(username='rec', password='pass12345')
        response = self.client.get(reverse('services:service_create'))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('services:service_list'))
