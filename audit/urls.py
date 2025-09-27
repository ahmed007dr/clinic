from django.urls import path
from .views import audit_list

urlpatterns = [
    path('', audit_list, name='audit_list'),
]