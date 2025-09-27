from django.urls import path
from .views import user_login, user_logout, user_create, user_list, user_update, user_delete

urlpatterns = [
    path('login/', user_login, name='login'),
    path('logout/', user_logout, name='logout'),
    path('create/', user_create, name='user_create'),
    path('', user_list, name='user_list'),
    path('<int:pk>/update/', user_update, name='user_update'),
    path('<int:pk>/delete/', user_delete, name='user_delete'),
]