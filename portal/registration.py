"""Self-registration from the public portal — off unless the group turns it on.

A form anyone can submit, writing medical history into a clinic, needs three
defences, and has them:

* **Opt-in.** `Tenant.portal_self_registration` defaults to off; a group that
  never enables it has no public write path at all.
* **Quarantine.** A submission becomes a patient with `needs_review=True`. It
  does not count against the plan, and reception confirms, merges or rejects it
  before it is anyone's patient.
* **No oracle.** The response is the same whether or not the phone number
  already belongs to a patient. Duplicates are shown to reception during
  review — never to the public.

The same `patients.intake.register_patient` staff registration uses does the
work, so the two doors cannot drift apart.
"""

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from api.serializers.intake import PortalRegistrationSerializer
from api.views.meta import choice_codes
from branches.models import Branch
from employees.models import Employee, Specialization
from patients.intake import RegistrationError, check_doctor_branch, register_patient
from patients.models import Patient

from .auth import enforce_csrf
from .views import PortalView


class RegistrationThrottle(AnonRateThrottle):
    scope = "portal_register"


class RegistrationClosed(Exception):
    pass


class _RegistrationView(PortalView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def closed(self):
        return not self.tenant.portal_self_registration


class RegisterOptionsView(_RegistrationView):
    """What the public form may offer: the group's clinics, specialties and
    doctors — names only. Served only when registration is open."""

    def get(self, request, slug):
        if self.closed():
            return Response({"detail": "التسجيل الإلكتروني غير متاح لهذه العيادة."}, status=404)
        doctors = Employee.objects.filter(employee_type__name="Doctor").select_related("branch") \
            .prefetch_related("specializations").order_by("name")
        return Response({
            "clinic": self.tenant.name,
            "choices": choice_codes(),
            "branches": [{"uuid": str(b.uuid), "name": b.name} for b in Branch.objects.order_by("name")],
            "specializations": [{"uuid": str(s.uuid), "name": s.name}
                                for s in Specialization.objects.order_by("name")],
            "doctors": [
                {"uuid": str(d.uuid), "name": d.name, "branch": str(d.branch.uuid) if d.branch else None,
                 "specializations": [str(s.uuid) for s in d.specializations.all()]}
                for d in doctors
            ],
        })


class RegisterView(_RegistrationView):
    throttle_classes = [RegistrationThrottle]

    def post(self, request, slug):
        enforce_csrf(request)
        if self.closed():
            return Response({"detail": "التسجيل الإلكتروني غير متاح لهذه العيادة."}, status=404)
        serializer = PortalRegistrationSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        personal = dict(data["personal"])
        if personal.get("branch") is None:
            return Response({"personal": {"branch": ["اختر العيادة."]}}, status=400)
        try:
            check_doctor_branch(data["visit"].get("requested_doctor"), personal["branch"])
        except RegistrationError as error:
            return Response({"visit": {"requested_doctor": [str(error)]}}, status=400)

        register_patient(
            tenant=self.tenant, personal=personal, visit=data["visit"],
            history=data.get("history"), referral=data.get("referral"),
            consent=data["consent"], actor=None, source=Patient.RegistrationSource.PORTAL,
        )
        # The same answer for a new person and for someone already on file.
        return Response({"detail": "تم استلام بياناتك. ستتواصل معك العيادة لتأكيد التسجيل."}, status=201)


class PublicLinksView(PortalView):
    """The group's clinics' social and contact links, for the portal's public
    pages (sign-in, registration). Public on purpose — these are the links a
    clinic publishes anyway — and only the ones each clinic filled in."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, slug):
        from branches.printing import link_items

        clinics = []
        for branch in Branch.objects.filter(is_active=True).order_by("name"):
            links = link_items(branch.print_links)
            if links:
                clinics.append({"name": branch.name, "links": links})
        return Response({"clinic": self.tenant.name, "clinics": clinics})
