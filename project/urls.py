
# project/urls.py
from django.contrib import admin
from django.urls import include, path, re_path

from api.spa import spa_index
from django.conf.urls.static import static
from django.conf import settings
from django.http import HttpResponseNotFound
from django.shortcuts import redirect

def unknown_path(request, unused_path):
    """Any other address. A person lands in the React app; a client of the API
    gets the 404 it asked for — a redirect to an HTML page is what makes an API
    call look like it hangs, and it would hide a mistyped endpoint."""
    if unused_path.startswith('api/'):
        return HttpResponseNotFound()
    return redirect('/app/')


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

    path('patients/', include(('patients.urls', 'patients'), namespace="patients")),
    path('appointments/', include(('appointments.urls', 'appointments'), namespace='appointments')),
    path('billing/', include(('billing.urls', 'billing'), namespace="billing")),
    path('audit/', include(('audit.urls', 'audit'), namespace="audit")),
    path('medical/', include(('medical.urls', 'medical'), namespace='medical')),
    # SaaS operators only (platform_admin.permissions). Mounted separately
    # from /admin/, which is Django's own and stays as it is.
    path('platform/', include(('platform_admin.urls', 'platform_admin'), namespace='platform_admin')),

    # The React application is the front door, and the only interface. What
    # is still served by Django is what React links to for the browser to print
    # or download: receipts, tickets, the shift report, the prescription and the
    # intake form, the PDF / Excel exports, and the audit log page. Every other
    # old address — a stale bookmark, the old login or dashboard — lands here.
    # A literal path rather than reverse('spa'): that pattern's optional
    # group is not something to trust reverse() with on every request.
    # The bare domain is the public directory of clinics — the store every
    # visitor sees first — served in place, with no redirect and no /app in the
    # address (api/spa.py; the page itself is api/directory.py's data). Staff
    # use /app/; a stale bookmark below still lands there.
    path('', spa_index, name='index'),
    path('<path:unused_path>/', unknown_path),

] 
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)