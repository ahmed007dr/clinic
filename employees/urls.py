from django.urls import path
from .views import (
    employee_create, employee_list, employee_update, employee_delete,
    employee_type_create, employee_type_list, employee_type_update, employee_type_delete,
    specialization_create, specialization_list, specialization_update, specialization_delete
)


app_name = "employees"

urlpatterns = [
    path('create/', employee_create, name='employee_create'),
    path('', employee_list, name='employee_list'),
    path('<uuid:uuid>/update/', employee_update, name='employee_update'),
    path('<uuid:uuid>/delete/', employee_delete, name='employee_delete'),
    path('type/create/', employee_type_create, name='employee_type_create'),
    path('type/', employee_type_list, name='employee_type_list'),
    path('type/<uuid:uuid>/update/', employee_type_update, name='employee_type_update'),
    path('type/<uuid:uuid>/delete/', employee_type_delete, name='employee_type_delete'),
    path('specialization/create/', specialization_create, name='specialization_create'),
    path('specialization/', specialization_list, name='specialization_list'),
    path('specialization/<uuid:uuid>/update/', specialization_update, name='specialization_update'),
    path('specialization/<uuid:uuid>/delete/', specialization_delete, name='specialization_delete'),
]