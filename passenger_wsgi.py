"""Passenger entry point for cPanel shared hosting.

cPanel's "Setup Python App" looks for this file at the application root and
imports `application` from it. Passenger already runs it under the virtualenv
the app was configured with, so there is no interpreter shim here — if you are
not using Setup Python App, see docs/10-deployment-runbook.md.

The previous version of this file hardcoded `/home/odayscom/src`, which meant it
could only ever work on one hosting account, and it had been commented out in
its entirety since 2025-09-29 — so it defined no `application` at all and
Passenger could not have booted from it. Both problems are fixed by deriving the
path from this file's own location.
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# insert, not append: the project's own packages must win over anything of the
# same name in site-packages.
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# setdefault, so a value configured in the Python App UI or the environment
# still wins over this default.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")

from django.core.wsgi import get_wsgi_application  # noqa: E402  (path set above)

application = get_wsgi_application()
