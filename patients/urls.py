from django.urls import path
from .views import patient_create, patient_list, patient_detail, patient_update, patient_delete

urlpatterns = [
    path('create/', patient_create, name='patient_create'),
    path('', patient_list, name='patient_list'),
    path('<int:pk>/', patient_detail, name='patient_detail'),
    path('<int:pk>/update/', patient_update, name='patient_update'),
    path('<int:pk>/delete/', patient_delete, name='patient_delete'),
]