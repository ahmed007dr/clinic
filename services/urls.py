from django.urls import path
from .views import service_create, service_list, service_update, service_delete

urlpatterns = [
    path('create/', service_create, name='service_create'),
    path('', service_list, name='service_list'),
    path('<int:pk>/update/', service_update, name='service_update'),
    path('<int:pk>/delete/', service_delete, name='service_delete'),
]