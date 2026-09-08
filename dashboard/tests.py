"""Static asset integrity.

The application shipped for some time with no static files in version control
at all: `base.html` loaded twelve vendor assets, `static/` was gitignored, and
the only copy lived in a `static.zip` that had been deleted. A fresh clone
rendered completely unstyled and nothing caught it, because a missing asset is
a silent 404 in the browser rather than a failure on the server.

These tests make that condition fail loudly instead.
"""

import re
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import SimpleTestCase

# {% static 'x' %} and {% static "x" %}, ignoring anything built from variables.
STATIC_TAG = re.compile(r"""\{%\s*static\s+['"]([^'"]+)['"]\s*%\}""")


def referenced_assets():
    """Every literal static path used by any template outside static/ itself."""
    root = Path(settings.BASE_DIR)
    found = {}
    for template in root.rglob("*.html"):
        parts = template.relative_to(root).parts
        if parts[0] in {"static", "staticfiles", ".git", "venv"}:
            continue
        text = template.read_text(encoding="utf-8", errors="ignore")
        for asset in STATIC_TAG.findall(text):
            found.setdefault(asset, []).append(template.relative_to(root).as_posix())
    return found


class StaticAssetReferenceTests(SimpleTestCase):
    def test_every_referenced_asset_resolves(self):
        """A template referencing an asset that isn't there is a broken page."""
        unresolved = {
            asset: templates
            for asset, templates in referenced_assets().items()
            if finders.find(asset) is None
        }
        self.assertEqual(
            unresolved,
            {},
            "static files referenced by templates but not found:\n"
            + "\n".join(f"  {a} <- {', '.join(t)}" for a, t in sorted(unresolved.items())),
        )

    def test_templates_actually_reference_assets(self):
        """Guards the guard: if the scan silently matched nothing, the test
        above would pass while asserting nothing at all."""
        self.assertGreater(len(referenced_assets()), 10)

    def test_the_theme_bundle_is_present(self):
        """jQuery and Bootstrap ship inside vendor.bundle.base.js rather than
        as separate files — templates must not reintroduce standalone copies."""
        self.assertIsNotNone(finders.find("vendors/base/vendor.bundle.base.js"))

    def test_no_template_loads_a_duplicate_jquery_or_bootstrap(self):
        duplicates = {"vendors/jquery/jquery.min.js",
                      "vendors/bootstrap/js/bootstrap.bundle.min.js"}
        offenders = {a: t for a, t in referenced_assets().items() if a in duplicates}
        self.assertEqual(offenders, {}, f"bundle already provides these: {offenders}")

    def test_datatables_translations_are_served_locally(self):
        """The Arabic translation used to be fetched from a CDN at runtime, so
        the interface degraded to English whenever the clinic's connection did."""
        root = Path(settings.BASE_DIR)
        offenders = [
            p.relative_to(root).as_posix()
            for p in root.rglob("*.html")
            if p.relative_to(root).parts[0] not in {"static", "staticfiles"}
            and "cdn.datatables.net" in p.read_text(encoding="utf-8", errors="ignore")
        ]
        self.assertEqual(offenders, [], f"templates still calling a CDN: {offenders}")
        self.assertIsNotNone(finders.find("vendors/datatables/i18n-ar.json"))
