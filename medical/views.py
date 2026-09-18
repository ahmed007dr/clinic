"""The printable prescription — the one server-rendered clinical page. The
clinical record itself is the React app and the API."""

from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404, render

from accounts.roles import is_front_desk

from .models import Allergy, Prescription
from .permissions import can_view_clinical, scoped_to_user


def _get_prescription(request, uuid):
    # A prescription has no branch of its own — it inherits the visit's.
    return get_object_or_404(
        scoped_to_user(Prescription.objects.all(), request.user, "visit__branch"),
        uuid=uuid,
    )


@login_required
@user_passes_test(lambda user: can_view_clinical(user) or is_front_desk(user))
def prescription_print(request, uuid):
    """Print-friendly view. Rendered as HTML rather than generated as a PDF:
    the browser handles Arabic shaping and RTL correctly, which the reportlab
    exporter used elsewhere does not.

    Open to the front desk as well (the group owner's rule, 2026-09-11):
    reception prints the sheet for the doctor to sign. It is the one clinical
    page they reach — the printed prescription, which the patient is handed
    anyway — and only within their own clinic."""
    from branches.printing import doctor_signature, letterhead

    prescription = _get_prescription(request, uuid)
    return render(request, "medical/prescription_print.html", {
        # The clinic's own letterhead — the same one as its intake form.
        "letterhead": letterhead(prescription.visit.branch, request),
        "doctor_signature": doctor_signature(prescription.doctor) if prescription.doctor else None,
        "prescription": prescription,
        "patient": prescription.patient,
        "allergies": Allergy.objects.filter(patient=prescription.patient),
    })
