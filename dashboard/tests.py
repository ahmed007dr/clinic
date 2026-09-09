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
        offenders = self.templates_containing("cdn.datatables.net")
        self.assertEqual(offenders, [], f"templates still calling a CDN: {offenders}")
        self.assertIsNotNone(finders.find("vendors/datatables/i18n-ar.json"))

    def templates_containing(self, needle):
        """App templates only — `static/` holds vendor documentation that is not
        served to users and is gitignored."""
        root = Path(settings.BASE_DIR)
        return sorted(
            p.relative_to(root).as_posix()
            for p in root.rglob("*.html")
            if p.relative_to(root).parts[0] not in {"static", "staticfiles", "venv"}
            and needle in p.read_text(encoding="utf-8", errors="ignore")
        )

    def test_no_template_loads_an_asset_from_an_external_host(self):
        """Generalises the datatables check to every remote asset, because the
        same failure kept recurring in a new place.

        The Arabic webfont was fetched from Google on every page load, including
        the prescription print sheet — so printing a prescription on a flaky
        connection silently fell back to a system font, and every view of a
        medical record announced itself to a third party. A clinic application
        has to render correctly with no internet at all.

        Anchor hrefs are not the concern here; this looks only at things the page
        *loads*.
        """
        remote_asset = re.compile(
            r"""<(?:link|script|img|source|iframe)\b[^>]*?
                 (?:href|src)\s*=\s*["'](?:https?:)?//""",
            re.IGNORECASE | re.VERBOSE,
        )
        root = Path(settings.BASE_DIR)
        offenders = {}
        for path in root.rglob("*.html"):
            relative = path.relative_to(root)
            if relative.parts[0] in {"static", "staticfiles", "venv"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            hits = remote_asset.findall(text)
            if hits:
                offenders[relative.as_posix()] = len(hits)
        self.assertEqual(
            offenders, {},
            "these templates load assets from an external host, so the page "
            f"renders differently without internet access: {offenders}",
        )

    def test_the_arabic_webfont_is_served_from_the_repository(self):
        """The replacement for that Google Fonts request. Both files are needed:
        woff2 for browsers, and the TTF for reportlab, which cannot read woff2."""
        self.assertIsNotNone(finders.find("css/cairo.css"))
        self.assertIsNotNone(finders.find("fonts/cairo/Cairo-subset.woff2"))
        self.assertIsNotNone(finders.find("fonts/cairo/Cairo.ttf"))
        self.assertIsNotNone(
            finders.find("fonts/cairo/OFL.txt"),
            "the SIL Open Font Licence must ship alongside the font",
        )

    def test_the_font_face_rule_points_at_files_that_exist(self):
        """A stylesheet that references a missing font fails silently — the
        browser just substitutes something else, which is the bug this replaced."""
        css = Path(finders.find("css/cairo.css")).read_text(encoding="utf-8")
        self.assertIn("@font-face", css)
        referenced = re.findall(r"url\(['\"]?\.\./([^'\")]+)['\"]?\)", css)
        self.assertTrue(referenced, "the @font-face rule references no files")
        for asset in referenced:
            with self.subTest(asset=asset):
                self.assertIsNotNone(
                    finders.find(asset), f"@font-face points at a missing file: {asset}"
                )
