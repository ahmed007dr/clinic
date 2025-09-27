from django.urls import path
from .views import appointment_create, appointment_list, appointment_detail, appointment_update, appointment_delete, waiting_list, waiting_list_data



app_name = "appointments"



urlpatterns = [
    path('', appointment_list, name='appointment_list'),
    path('create/', appointment_create, name='appointment_create'),
    path('<int:pk>/', appointment_detail, name='appointment_detail'),
    path('<int:pk>/update/', appointment_update, name='appointment_update'),
    path('<int:pk>/delete/', appointment_delete, name='appointment_delete'),
    path('waiting/', waiting_list, name='waiting_list'),
    path('waiting/data/', waiting_list_data, name='waiting_list_data'),
]