"""
URL configuration for project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
# project/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf.urls.static import static
from django.conf import settings
from django.shortcuts import redirect

def home_redirect(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return redirect('login')



urlpatterns = [
    path('admin/', admin.site.urls),
    
    path('accounts/', include(('accounts.urls', 'accounts'), namespace="accounts")),
    path('patients/', include(('patients.urls', 'patients'), namespace="patients")),
    path('appointments/', include(('appointments.urls', 'appointments'), namespace='appointments')),
    path('billing/', include(('billing.urls', 'billing'), namespace="billing")),
    path('branches/', include(('branches.urls', 'branches'), namespace="branches")),
    path('employees/', include(('employees.urls', 'employees'), namespace="employees")),
    path('notifications/', include(('notifications.urls', 'notifications'), namespace="notifications")),
    path('audit/', include(('audit.urls', 'audit'), namespace="audit")),
    path('services/', include(('services.urls', 'services'), namespace='services')),
    path('dashboard/', include(('dashboard.urls', 'dashboard'), namespace="dashboard")),

    path('', lambda request: redirect('login')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
