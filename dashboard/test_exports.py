"""Coverage for the two third-party libraries that had none: reportlab and pillow.

These live here rather than beside the code they test because `utils/` has no
`__init__.py` — it is an implicit namespace package, and test discovery through
one is unreliable. `dashboard` is an installed app and already hosts the other
cross-cutting checks (static-asset integrity).

Why they exist at all: `reportlab` and `pillow` are the only two dependencies
that produce binary output, and nothing verified either. That makes a version
bump unfalsifiable — the suite would stay green while PDF export produced
garbage, because no test ever looked at the bytes. Written before bumping
either, so the bump has something to fail against.

Note for whoever touches the PDF path next: `utils/utils.py::export_pdf` is the
live one, used by billing, patients and services. `utils/export_pdf.py` defines
a *different* function with the same name and is imported by nothing — dead
code, left alone here rather than deleted as an unrelated change.
"""

import tempfile
from io import BytesIO

import openpyxl
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings

from utils.utils import export_excel, export_pdf

HEADERS = ["الاسم", "الهاتف", "المبلغ"]
ROWS = [
    ["أحمد محمد", "01001234567", "1200.00"],
    ["منى علي", "01112345678", "450.50"],
]


class PdfExportTests(SimpleTestCase):
    """reportlab. The assertions are about the bytes, not just the status code —
    a broken PDF still comes back as a 200 with a PDF content type."""

    def response(self):
        return export_pdf(ROWS, HEADERS, "تقرير المرضى", "patients-report")

    def test_the_response_is_served_as_a_pdf_attachment(self):
        response = self.response()
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("patients-report.pdf", response["Content-Disposition"])

    def test_the_body_is_a_structurally_valid_pdf(self):
        body = self.response().content
        self.assertTrue(body.startswith(b"%PDF-"), "missing the PDF magic header")
        self.assertIn(b"%%EOF", body, "PDF is not terminated")
        # A document containing a title and a 3x3 table is not 200 bytes. This
        # catches an "empty but well-formed" regression, which is what a
        # platypus API change would most likely produce.
        self.assertGreater(len(body), 1000, f"suspiciously small PDF: {len(body)} bytes")

    def test_an_empty_dataset_still_produces_a_document(self):
        """Reached whenever a report matches nothing — a crash here would be a
        500 on an ordinary empty search."""
        body = export_pdf([], HEADERS, "فارغ", "empty").content
        self.assertTrue(body.startswith(b"%PDF-"))


class ExcelExportTests(SimpleTestCase):
    """openpyxl. Read back through openpyxl rather than trusting the bytes, so
    the test fails if the sheet is written but empty."""

    def test_the_workbook_round_trips_with_its_data(self):
        response = export_excel(ROWS, HEADERS, "المرضى", "patients-report")
        self.assertIn("spreadsheetml", response["Content-Type"])
        self.assertIn("patients-report.xlsx", response["Content-Disposition"])

        body = response.content
        self.assertTrue(body.startswith(b"PK"), "not a zip container, so not xlsx")

        workbook = openpyxl.load_workbook(BytesIO(body))
        sheet = workbook.active
        values = [[cell.value for cell in row] for row in sheet.iter_rows()]
        flat = [v for row in values for v in row if v is not None]

        self.assertIn("المرضى", flat)            # the title row
        self.assertIn("الاسم", flat)             # the header row
        self.assertIn("أحمد محمد", flat)         # a data row, Arabic intact
        self.assertIn("01001234567", flat)


class ImageFieldTests(TestCase):
    """pillow. Django uses it to validate and to read image dimensions, so a
    pillow bump can break uploads without any of our code changing."""

    def png_bytes(self):
        """Generated with pillow rather than hard-coded, so the test exercises
        the installed version at both ends."""
        from PIL import Image

        buffer = BytesIO()
        Image.new("RGB", (32, 24), (200, 30, 30)).save(buffer, format="PNG")
        return buffer.getvalue()

    def test_django_accepts_a_real_image(self):
        """This is the pillow integration point: forms.ImageField opens the
        upload with pillow and calls verify()."""
        from django import forms

        cleaned = forms.ImageField().clean(
            SimpleUploadedFile("logo.png", self.png_bytes(), content_type="image/png")
        )
        self.assertEqual(cleaned.image.size, (32, 24))
        self.assertEqual(cleaned.image.format, "PNG")

    def test_django_rejects_a_file_that_is_not_an_image(self):
        """The other half — a bump that silently stopped validating would be
        worse than one that broke loudly."""
        from django import forms

        with self.assertRaises(Exception):
            forms.ImageField().clean(
                SimpleUploadedFile("evil.png", b"not an image at all",
                                   content_type="image/png")
            )

    def test_a_patient_photo_saves_and_reads_back(self):
        """End to end through the model field and storage. MEDIA_ROOT is
        redirected so the suite does not litter the project's media/ directory."""
        from patients.models import Patient

        from tenants.context import tenant_context
        from tenants.models import Tenant

        tenant = Tenant.objects.first()
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                with tenant_context(tenant):
                    patient = Patient.all_objects.create(
                        tenant=tenant, name="Photo Patient",
                        photo=SimpleUploadedFile(
                            "p.png", self.png_bytes(), content_type="image/png"
                        ),
                    )
                    patient.refresh_from_db()
                    self.assertTrue(patient.photo.name.endswith(".png"))
                    self.assertEqual(patient.photo.width, 32)
                    self.assertEqual(patient.photo.height, 24)
                    with patient.photo.open("rb") as handle:
                        self.assertTrue(handle.read().startswith(b"\x89PNG"))
