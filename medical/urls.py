"""The printable prescription. (The clinical record is the React app and /api/.)"""

from django.urls import path

from .views import prescription_print

app_name = "medical"

urlpatterns = [
    path("prescription/<uuid:uuid>/print/", prescription_print, name="prescription_print"),
]
