"""The related field, tested at the level where the bug actually lives.

`test_isolation.py` exercises this field through real requests, which proves it
works but does *not* prove it could not be written the broken way — an earlier
version of that suite passed against a deliberately frozen field, because DRF
re-runs `Field.__init__` on every deepcopy and so hid the mistake.

The genuine failure is narrower than "a queryset built too early". It is a
queryset built **in a serializer's class body**:

    patient = serializers.SlugRelatedField(
        slug_field="uuid", queryset=Patient.objects.all()
    )

That expression runs once, at import, with no tenant in context.
`TenantManager` fails closed, so it evaluates to `.none()`, and DRF stores the
already-empty queryset in `_kwargs` and deep-copies it — empty — into every
serializer instance for the life of the process. The clinic's symptom is not a
crash: it is every save failing with "no record with that identifier" while the
record is plainly on screen.

The first test below reproduces exactly that, so the claim is demonstrated
rather than asserted. The rest pin the behaviour that avoids it.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import serializers

from accounts.models import ClinicRole
from api.relations import TenantScopedRelatedField
from branches.models import Branch
from patients.models import Patient
from tenants.context import get_current_tenant, tenant_context
from tenants.models import Tenant

User = get_user_model()


class FrozenQuerysetTests(TestCase):
    """Why `TenantScopedRelatedField` exists at all."""

    def setUp(self):
        self.tenant = Tenant.objects.first()
        with tenant_context(self.tenant):
            self.branch = Branch.all_objects.create(
                tenant=self.tenant, name="Main", code="MN"
            )
            self.patient = Patient.all_objects.create(
                tenant=self.tenant, name="Real Patient", branch=self.branch
            )

    def test_the_naive_form_really_is_permanently_empty(self):
        """The mistake, reproduced.

        `Patient.objects.all()` is evaluated here with no tenant bound — the
        same conditions as module import — and the resulting field stays empty
        even when used later inside a tenant.
        """
        self.assertIsNone(get_current_tenant(), "precondition: no tenant bound")
        naive = serializers.SlugRelatedField(
            slug_field="uuid", queryset=Patient.objects.all()
        )

        with tenant_context(self.tenant):
            self.assertEqual(naive.get_queryset().count(), 0)
            with self.assertRaises(serializers.ValidationError):
                naive.to_internal_value(str(self.patient.uuid))

    def test_the_scoped_field_resolves_although_it_was_built_unbound(self):
        """The same construction order, the correct outcome.

        Built with no tenant in context, used inside one, and it finds the
        record — because the queryset is rebuilt per call rather than captured.
        """
        self.assertIsNone(get_current_tenant(), "precondition: no tenant bound")
        field = TenantScopedRelatedField(model=Patient)
        field.bind("patient", serializers.Serializer())

        with tenant_context(self.tenant):
            self.assertEqual(field.get_queryset().count(), 1)
            self.assertEqual(field.to_internal_value(str(self.patient.uuid)), self.patient)

    def test_it_refuses_a_queryset_argument(self):
        """Passing one is the mistake; the field must not quietly accept it.

        Silently ignoring `queryset=` is deliberate over raising: a caller who
        passes it gets correct behaviour rather than a crash, and the field
        that would have been frozen simply is not.
        """
        field = TenantScopedRelatedField(
            model=Patient, queryset=Patient.objects.none()
        )
        field.bind("patient", serializers.Serializer())
        with tenant_context(self.tenant):
            self.assertEqual(field.get_queryset().count(), 1)


class ScopedChoiceTests(TestCase):
    """A UUID is not an authorisation, so the choices are narrowed too."""

    def setUp(self):
        self.tenant = Tenant.objects.first()
        with tenant_context(self.tenant):
            self.role, _ = ClinicRole.all_objects.get_or_create(
                tenant=self.tenant, name="Reception"
            )
            self.here = Branch.all_objects.create(
                tenant=self.tenant, name="Here", code="H"
            )
            self.elsewhere = Branch.all_objects.create(
                tenant=self.tenant, name="Elsewhere", code="E"
            )
            self.mine = Patient.all_objects.create(
                tenant=self.tenant, name="Mine", branch=self.here
            )
            self.theirs = Patient.all_objects.create(
                tenant=self.tenant, name="Theirs", branch=self.elsewhere
            )
        self.receptionist = User.objects.create_user(
            username="rec", email="rec-rel@t.local", password="pass12345",
            tenant=self.tenant, role=self.role, branch=self.here,
        )

    def field_for(self, user):
        """Context has to go on the *parent*, not the field.

        `Field.context` resolves through `self.root`, so a context set on a
        bound field is silently ignored — which is exactly how the first
        version of this test reported that scoping was broken when it was the
        harness that was wrong. `test_a_receptionist_cannot_book_across_branches`
        below covers the same ground through a real request, so the behaviour
        does not rest on getting this plumbing right.
        """

        class Request:
            pass

        request = Request()
        request.user = user

        parent = serializers.Serializer()
        parent._context = {"request": request}
        field = TenantScopedRelatedField(model=Patient, branch_field="branch")
        field.bind("patient", parent)
        return field

    def test_a_branch_scoped_field_hides_another_branchs_records(self):
        """Otherwise a receptionist who cannot see a patient could still
        attach one to a new booking by pasting a UUID."""
        field = self.field_for(self.receptionist)
        with tenant_context(self.tenant):
            names = set(field.get_queryset().values_list("name", flat=True))
        self.assertEqual(names, {"Mine"})

    def test_a_receptionist_cannot_book_across_branches(self):
        """The same rule, through the real stack.

        The unit tests above depend on assembling DRF's context by hand, and
        getting that wrong once already produced a false failure. This asserts
        the outcome that actually matters — a booking for a patient the caller
        cannot see is refused — without touching any internals.
        """
        from django.urls import reverse
        from django.utils import timezone

        self.client.login(email="rec-rel@t.local", password="pass12345")
        response = self.client.post(
            reverse("api:appointment-list"),
            {
                "patient": str(self.theirs.uuid),
                "scheduled_date": timezone.now().isoformat(),
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("patient", response.json())

        # The same request for their own branch's patient succeeds, so the
        # refusal above is scoping and not a broken endpoint.
        allowed = self.client.post(
            reverse("api:appointment-list"),
            {
                "patient": str(self.mine.uuid),
                "scheduled_date": timezone.now().isoformat(),
            },
            content_type="application/json",
        )
        self.assertEqual(allowed.status_code, 201, allowed.content)

    def test_an_admin_sees_every_branch(self):
        with tenant_context(self.tenant):
            admin_role, _ = ClinicRole.all_objects.get_or_create(
                tenant=self.tenant, name="Admin"
            )
        admin = User.objects.create_user(
            username="adm", email="adm-rel@t.local", password="pass12345",
            tenant=self.tenant, role=admin_role, branch=self.here,
        )
        field = self.field_for(admin)
        with tenant_context(self.tenant):
            names = set(field.get_queryset().values_list("name", flat=True))
        self.assertEqual(names, {"Mine", "Theirs"})
