from django.urls import path
from .views import branch_create, branch_list, branch_update, branch_delete


app_name = "branches"



urlpatterns = [
    path('create/', branch_create, name='branch_create'),
    path('', branch_list, name='branch_list'),
    path('<uuid:uuid>/update/', branch_update, name='branch_update'),
    path('<uuid:uuid>/delete/', branch_delete, name='branch_delete'),
]