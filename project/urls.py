
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

    #path('', lambda request: redirect('login')),
    path('', lambda request: redirect('accounts:login'), name='index'),
    path('<path:unused_path>/', lambda request, unused_path: redirect('login')),

] 
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)