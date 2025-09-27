from django.urls import path
from .views import notification_list, notification_mark_read


app_name = "notification"


urlpatterns = [
    path('', notification_list, name='notification_list'),
    path('<int:pk>/mark-read/', notification_mark_read, name='notification_mark_read'),
]