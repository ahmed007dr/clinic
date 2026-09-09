from django.urls import path

from .views import tenant_change_plan, tenant_detail, tenant_list, tenant_set_status

app_name = "platform_admin"

urlpatterns = [
    path("", tenant_list, name="tenant_list"),
    path("tenant/<uuid:uuid>/", tenant_detail, name="tenant_detail"),
    # Both state changes are POST-only; see views.py.
    path("tenant/<uuid:uuid>/status/", tenant_set_status, name="tenant_set_status"),
    path("tenant/<uuid:uuid>/plan/", tenant_change_plan, name="tenant_change_plan"),
]
