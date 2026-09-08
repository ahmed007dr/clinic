from django.urls import path

from .views import (
    allergy_create,
    prescription_create,
    prescription_detail,
    prescription_print,
    prescription_update,
    session_create,
    session_detail,
    session_update,
    treatment_plan_create,
    treatment_plan_detail,
    treatment_plan_update,
    visit_create,
    visit_detail,
    visit_update,
)

app_name = "medical"

urlpatterns = [
    path("patient/<uuid:patient_uuid>/visit/new/", visit_create, name="visit_create"),
    path("patient/<uuid:patient_uuid>/allergy/new/", allergy_create, name="allergy_create"),
    path("visit/<uuid:uuid>/", visit_detail, name="visit_detail"),
    path("visit/<uuid:uuid>/update/", visit_update, name="visit_update"),
    path("visit/<uuid:visit_uuid>/prescription/new/", prescription_create, name="prescription_create"),
    path("prescription/<uuid:uuid>/", prescription_detail, name="prescription_detail"),
    path("prescription/<uuid:uuid>/update/", prescription_update, name="prescription_update"),
    path("prescription/<uuid:uuid>/print/", prescription_print, name="prescription_print"),
    path("patient/<uuid:patient_uuid>/plan/new/", treatment_plan_create, name="treatment_plan_create"),
    path("plan/<uuid:uuid>/", treatment_plan_detail, name="treatment_plan_detail"),
    path("plan/<uuid:uuid>/update/", treatment_plan_update, name="treatment_plan_update"),
    path("plan/<uuid:plan_uuid>/session/new/", session_create, name="session_create"),
    path("session/<uuid:uuid>/", session_detail, name="session_detail"),
    path("session/<uuid:uuid>/update/", session_update, name="session_update"),
]
