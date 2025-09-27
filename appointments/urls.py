from django.urls import path
from .views import appointment_create, appointment_list

urlpatterns = [
    path('', appointment_list, name='appointment_list'),
    path('create/', appointment_create, name='appointment_create'),
]