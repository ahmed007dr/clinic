from django.urls import path

from . import views
from .views import (
    patient_create,
    patient_list,
    patient_detail,
    patient_update,
    patient_delete,
    patient_list_export,
)

app_name = "patients"

urlpatterns = [
    path('create/', patient_create, name='patient_create'),
    path('print/intake/', views.intake_form_print, name='intake_form_print'),
    path('', patient_list, name='patient_list'),
    path('export/', patient_list_export, name='patient_list_export'),
    path('<uuid:uuid>/', patient_detail, name='patient_detail'),
    path('<uuid:uuid>/update/', patient_update, name='patient_update'),
    path('<uuid:uuid>/delete/', patient_delete, name='patient_delete'),
]