from django.urls import path
from .views import (
    service_create, service_list, service_update, service_delete,
     service_list_export
)

app_name = "services"

urlpatterns = [
    path('create/', service_create, name='service_create'),
    path('', service_list, name='service_list'),
    path('<uuid:uuid>/update/', service_update, name='service_update'),
    path('<uuid:uuid>/delete/', service_delete, name='service_delete'),
    path('export/', service_list_export, name='service_list_export'),
]
