
# project/urls.py
from django.contrib import admin
from django.urls import include, path, re_path

from api.spa import spa_index
from django.conf.urls.static import static
from django.conf import settings
from django.shortcuts import redirect

def home_redirect(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return redirect('login')



urlpatterns = [
    path('admin/', admin.site.urls),

    # The REST API the React front end talks to. It must stay above the
    # catch-all at the bottom of this list, which redirects every unmatched
    # path to the login page — an API call that gets a 302 to an HTML form
    # instead of a 401 is the kind of thing a client reports as "it hangs".
    path('api/', include('api.urls')),

    # The React application. Every path under /app/ returns the same shell so
    # client-side routes survive a reload; see api/spa.py.
    re_path(r'^app(?:/(?P<path>.*))?$', spa_index, name='spa'),

    path('accounts/', include(('accounts.urls', 'accounts'), namespace="accounts")),
    path('patients/', include(('patients.urls', 'patients'), namespace="patients")),
    path('appointments/', include(('appointments.urls', 'appointments'), namespace='appointments')),
    path('billing/', include(('billing.urls', 'billing'), namespace="billing")),
    path('branches/', include(('branches.urls', 'branches'), namespace="branches")),
    path('employees/', include(('employees.urls', 'employees'), namespace="employees")),
    path('notifications/', include(('notifications.urls', 'notifications'), namespace="notifications")),
    path('audit/', include(('audit.urls', 'audit'), namespace="audit")),
    path('services/', include(('services.urls', 'services'), namespace='services')),
    path('medical/', include(('medical.urls', 'medical'), namespace='medical')),
    path('dashboard/', include(('dashboard.urls', 'dashboard'), namespace="dashboard")),
    # SaaS operators only (platform_admin.permissions). Mounted separately
    # from /admin/, which is Django's own and stays as it is.
    path('platform/', include(('platform_admin.urls', 'platform_admin'), namespace='platform_admin')),

    #path('', lambda request: redirect('login')),
    path('', lambda request: redirect('accounts:login'), name='index'),
    # 'login' is namespaced as 'accounts:login', so the un-namespaced name here
    # raised NoReverseMatch — every unmatched URL 500'd instead of redirecting.
    path('<path:unused_path>/', lambda request, unused_path: redirect('accounts:login')),

] 
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)