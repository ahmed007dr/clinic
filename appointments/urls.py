"""The queue ticket, printed from React. (The old booking screens are gone — that
is the React app and /api/appointments/.)"""

from django.urls import path

from .views import appointment_ticket_print

app_name = "appointments"

urlpatterns = [
    path('<uuid:uuid>/ticket/', appointment_ticket_print, name='appointment_ticket_print'),
]
