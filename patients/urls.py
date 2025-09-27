# patients/urls.py
from django.urls import path
from .views import (
    patient_create,
    patient_list,
    patient_detail,
    patient_update,
    patient_delete,
    patient_list_data,
    patient_list_export,
)

app_name = "patients"

urlpatterns = [
    path('create/', patient_create, name='patient_create'),
    path('', patient_list, name='patient_list'),
    path('data/', patient_list_data, name='patient_list_data'),   
    path('export/', patient_list_export, name='patient_list_export'),
    path('<int:pk>/', patient_detail, name='patient_detail'),
    path('<int:pk>/update/', patient_update, name='patient_update'),
    path('<int:pk>/delete/', patient_delete, name='patient_delete'),
]
