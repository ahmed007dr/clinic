"""The server-rendered pages of patients that React links to: the printable intake
form and the PDF / Excel export. (The old list / create / edit screens are gone —
that is the React app and /api/patients/.)"""

from django.urls import path

from .views import intake_form_print, patient_list_export

app_name = "patients"

urlpatterns = [
    path('print/intake/', intake_form_print, name='intake_form_print'),
    path('export/', patient_list_export, name='patient_list_export'),
]
