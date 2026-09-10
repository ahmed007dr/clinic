"""Serve the React application's shell.

The built assets are ordinary static files — collectstatic picks them up from
`frontend/dist` (see STATICFILES_DIRS) and the web server serves them like any
other. Only `index.html` comes through Django, for two reasons:

* **Client-side routes.** `/app/patients/<uuid>` is a URL the React router
  understands and the file system does not. Every path under `/app/` answers
  with the same shell, and the router takes it from there. Without this, a
  reload or a bookmarked link returns 404.
* **The CSRF cookie.** `ensure_csrf_cookie` guarantees it exists before the app
  makes its first write, so a fresh browser's first form submission does not
  fail validation. `/api/auth/session/` sets it too; doing it here as well
  costs nothing and removes a race.

No authentication here: the shell holds no data. Everything it shows is fetched
from the API, which authorises every request.
"""

from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import ensure_csrf_cookie

SPA_INDEX = Path(settings.BASE_DIR) / "frontend" / "dist" / "spa" / "index.html"

NOT_BUILT = """<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8">
<title>الواجهة غير مبنية</title>
<body style="font-family:system-ui;padding:2rem;line-height:1.7">
<h1>واجهة React لم تُبنَ بعد</h1>
<p>شغّل الأمر التالي ثم <code>collectstatic</code>:</p>
<pre dir="ltr">cd frontend &amp;&amp; npm ci &amp;&amp; npm run build</pre>
<p>الشاشات القديمة ما زالت تعمل على <a href="/accounts/login/">/accounts/login/</a>.</p>
</body></html>"""


@ensure_csrf_cookie
def spa_index(request, path=""):
    try:
        html = SPA_INDEX.read_text(encoding="utf-8")
    except FileNotFoundError:
        # A clear page rather than a 500: the most likely cause is a deploy
        # that forgot the build step, and the fix is one command.
        return HttpResponse(NOT_BUILT, status=503)

    response = HttpResponse(html)
    # The shell must never be cached: it names the hashed asset files of the
    # current build, and a stale shell points at files the next deploy removed.
    response["Cache-Control"] = "no-store"
    return response
