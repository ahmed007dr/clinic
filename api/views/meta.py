"""The codes behind every choice the screens offer.

Screens translate codes into words (`frontend/src/i18n/*.json`); they never
keep their own copy of a list. When the backend adds a referral source, the
form offers it the next time it loads — and the translation test fails until
both languages have a word for it.
"""

from rest_framework.response import Response
from rest_framework.views import APIView

from api.permissions import IsClinicMember
from appointments.models import Appointment
from employees.models import Attendance
from medical.models import Allergy, ChronicCondition, PatientIntake, PatientMedicalProfile
from patients.models import Patient


def choice_codes():
    return {
        "gender": [code for code, _ in Patient.GENDER_CHOICES],
        "marital_status": [code for code, _ in Patient.MARITAL_STATUS_CHOICES],
        "referral_source": list(Patient.ReferralSource.values),
        "chronic_condition": list(ChronicCondition.values),
        "case_type": list(PatientIntake.CaseType.values),
        "symptom_onset": list(PatientIntake.Onset.values),
        "smoking_status": list(PatientMedicalProfile.Smoking.values),
        "allergy_severity": list(Allergy.Severity.values),
        "attendance_status": list(Attendance.Status.values),
        "appointment_status": [code for code, _ in Appointment.STATUS_CHOICES],
    }


class ChoicesView(APIView):
    permission_classes = [IsClinicMember]

    def get(self, request):
        return Response(choice_codes())
