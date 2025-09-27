from django.urls import path
from .views import payment_create, payment_list, payment_detail, expense_create, expense_list, expense_update, expense_delete, expense_category_create, expense_category_list, expense_category_update, expense_category_delete, financial_report

urlpatterns = [
    path('create/', payment_create, name='payment_create'),
    path('', payment_list, name='payment_list'),
    path('<int:pk>/', payment_detail, name='payment_detail'),
    path('expense/create/', expense_create, name='expense_create'),
    path('expense/', expense_list, name='expense_list'),
    path('expense/<int:pk>/update/', expense_update, name='expense_update'),
    path('expense/<int:pk>/delete/', expense_delete, name='expense_delete'),
    path('expense-category/create/', expense_category_create, name='expense_category_create'),
    path('expense-category/', expense_category_list, name='expense_category_list'),
    path('expense-category/<int:pk>/update/', expense_category_update, name='expense_category_update'),
    path('expense-category/<int:pk>/delete/', expense_category_delete, name='expense_category_delete'),
    path('financial-report/', financial_report, name='financial_report'),
]