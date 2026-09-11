"""A doctor's own footer on their prescriptions — written by them, approved
by the clinic (the group owner's rule, 2026-09-11).

    GET/PUT /api/me/doctor-profile/                  the signed-in doctor's
    GET     /api/doctor-profiles/?status=pending      management: to review
    POST    /api/doctor-profiles/<uuid>/approve/
    POST    /api/doctor-profiles/<uuid>/reject/       {note}

What the doctor saves waits in `pending_profile`; prescriptions keep printing
the last approved `public_profile` until the clinic's Admin (or the Owner)
approves the new one (branches/printing.py doctor_signature).
"""

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.roles import current_branch_id, is_clinic_admin, is_doctor, sees_all_branches
from api.permissions import IsClinicMember
from branches.printing import LINK_KINDS, LinkError, clean_profile, link_items
from employees.models import Employee


def profile_payload(employee):
    return {
        "doctor": str(employee.uuid),
        "doctor_name": employee.name,
        "branch_name": getattr(employee.branch, "name", None),
        "approved": employee.public_profile or {},
        "approved_links": link_items((employee.public_profile or {}).get("links")),
        "pending": employee.pending_profile,
        "pending_links": link_items((employee.pending_profile or {}).get("links")),
        "status": employee.profile_status,
        "note": employee.profile_review_note,
        "reviewed_at": employee.profile_reviewed_at,
        "link_kinds": [{"key": k, "label": v} for k, v in LINK_KINDS.items()],
    }


class MyDoctorProfileView(APIView):
    permission_classes = [IsClinicMember]

    def employee(self, request):
        employee = getattr(request.user, "employee", None) if is_doctor(request.user) else None
        if employee is None:
            raise PermissionDenied("هذه الصفحة لحسابات الأطباء المرتبطة بسجل طبيب.")
        return employee

    def get(self, request):
        return Response(profile_payload(self.employee(request)))

    def put(self, request):
        employee = self.employee(request)
        try:
            profile = clean_profile(request.data)
        except LinkError as error:
            raise ValidationError({"detail": str(error)})
        employee.pending_profile = profile
        employee.profile_status = "pending"
        employee.profile_review_note = ""
        employee.save(update_fields=["pending_profile", "profile_status", "profile_review_note"])
        return Response(profile_payload(employee))


def reviewable_doctors(user):
    """Doctors whose footer this user may approve: their clinic's (home or
    visiting), or every clinic's for the Owner."""
    doctors = Employee.objects.filter(employee_type__name="Doctor")
    if sees_all_branches(user):
        return doctors
    branch_id = current_branch_id(user)
    return doctors.filter(Q(branch_id=branch_id) | Q(extra_branches=branch_id)).distinct()


class DoctorProfileListView(APIView):
    permission_classes = [IsClinicMember]

    def get(self, request):
        if not is_clinic_admin(request.user):
            raise PermissionDenied("مراجعة روابط الأطباء لإدارة العيادة.")
        doctors = reviewable_doctors(request.user).select_related("branch").order_by("name")
        status = request.query_params.get("status")
        if status:
            doctors = doctors.filter(profile_status=status)
        return Response([profile_payload(doctor) for doctor in doctors])


class DoctorProfileDecisionView(APIView):
    permission_classes = [IsClinicMember]
    decision = None  # "approve" | "reject"

    def post(self, request, uuid):
        if not is_clinic_admin(request.user):
            raise PermissionDenied("اعتماد روابط الأطباء لإدارة العيادة.")
        doctor = get_object_or_404(reviewable_doctors(request.user), uuid=uuid)
        if doctor.profile_status != "pending" or doctor.pending_profile is None:
            raise ValidationError({"detail": "لا يوجد طلب بانتظار المراجعة لهذا الطبيب."})
        if self.decision == "approve":
            doctor.public_profile = doctor.pending_profile
            doctor.pending_profile = None
            doctor.profile_status = "approved"
            doctor.profile_review_note = ""
        else:
            doctor.profile_status = "rejected"
            doctor.profile_review_note = str(request.data.get("note") or "").strip()[:300]
        doctor.profile_reviewed_by = request.user
        doctor.profile_reviewed_at = timezone.now()
        doctor.save(update_fields=[
            "public_profile", "pending_profile", "profile_status", "profile_review_note",
            "profile_reviewed_by", "profile_reviewed_at",
        ])
        return Response(profile_payload(doctor))
