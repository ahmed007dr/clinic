"""The old server-rendered platform pages, retired.

The developer portal is the React application at `/app/platform` (docs/06
PLAT-000..). These addresses only redirect there, so bookmarks keep working.
"""

from django.urls import re_path
from django.views.generic import RedirectView

app_name = "platform_admin"

urlpatterns = [
    re_path(r"^.*$", RedirectView.as_view(url="/app/platform", permanent=True), name="retired"),
]
