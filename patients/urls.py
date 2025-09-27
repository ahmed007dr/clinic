from django.urls import path
from .views import patient_create

urlpatterns = [
    path('create/', patient_create, name='patient_create'),
]