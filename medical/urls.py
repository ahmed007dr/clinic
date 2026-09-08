from django.urls import path

from .views import (
    allergy_create,
    prescription_create,
    prescription_detail,
    prescription_print,
    prescription_update,
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
]
