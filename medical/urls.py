from django.urls import path

from .views import allergy_create, visit_create, visit_detail, visit_update

app_name = "medical"

urlpatterns = [
    path("patient/<uuid:patient_uuid>/visit/new/", visit_create, name="visit_create"),
    path("patient/<uuid:patient_uuid>/allergy/new/", allergy_create, name="allergy_create"),
    path("visit/<uuid:uuid>/", visit_detail, name="visit_detail"),
    path("visit/<uuid:uuid>/update/", visit_update, name="visit_update"),
]
