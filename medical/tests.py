"""Medical attachments — the storage and the validation, asserted directly.

The rest of the clinical record's rules (access, isolation, numbering, money,
the lab-result flow, upload and download) are tested through the API the React
app uses, in `api/tests/test_clinical_records.py`; the old screens they were
first written against no longer exist.
"""

import hashlib
import os
from pathlib import Path
from types import SimpleNamespace

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings

from .attachments import (
    attachment_storage,
    attachment_upload_path,
    checksum,
    validate_attachment,
)

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


def upload(name="report.pdf", content=PDF_BYTES, content_type="application/pdf"):
    return SimpleUploadedFile(name, content, content_type=content_type)


class AttachmentStorageTests(SimpleTestCase):
    """The storage decisions, asserted directly — these are what make the file
    bytes safe, and none of them is visible from the model."""

    def test_attachments_are_stored_outside_media_root(self):
        """A file under MEDIA_ROOT is a candidate for the web server to serve,
        and a file served that way has bypassed every check in the view layer.
        With DEBUG on, Django serves MEDIA_ROOT itself with no authentication.
        """
        attachments = Path(settings.MEDICAL_ATTACHMENTS_ROOT).resolve()
        media = Path(settings.MEDIA_ROOT).resolve()
        self.assertNotEqual(attachments, media)
        self.assertFalse(
            str(attachments).startswith(str(media) + os.sep),
            f"attachments are inside MEDIA_ROOT: {attachments}",
        )

    def test_the_storage_exposes_no_public_url(self):
        """`attachment.file.url` must fail rather than return a path. A template
        that reaches for it should break loudly, not render a link that leaks."""
        with self.assertRaises(ValueError):
            attachment_storage().url("tenant-1/whatever.pdf")

    def test_the_override_is_load_bearing_not_decorative(self):
        """Passing base_url=None does not achieve the above, which is easy to
        assume and wrong: None means "use the default", and the default is
        MEDIA_URL. A storage built that way hands out
        /media/tenant-1/<uuid>.pdf quite happily. This asserts the difference so
        nobody simplifies the override away."""
        from django.core.files.storage import FileSystemStorage

        naive = FileSystemStorage(
            location=str(settings.MEDICAL_ATTACHMENTS_ROOT), base_url=None
        )
        self.assertTrue(naive.url("tenant-1/whatever.pdf").startswith(settings.MEDIA_URL))

    def test_the_stored_name_is_random_and_tenant_partitioned(self):
        """The uploaded name is attacker-controlled: it can carry separators, be
        absurdly long, collide, or name the patient in a directory listing."""
        instance = SimpleNamespace(tenant_id=7)
        path = attachment_upload_path(instance, "scan.pdf")
        self.assertTrue(path.startswith("tenant-7/"))
        self.assertTrue(path.endswith(".pdf"))
        self.assertNotIn("scan", path)
        self.assertNotEqual(path, attachment_upload_path(instance, "scan.pdf"))

    def test_a_traversing_filename_cannot_escape_the_directory(self):
        instance = SimpleNamespace(tenant_id=7)
        for hostile in ("../../etc/passwd.pdf", "..\\..\\windows\\evil.pdf",
                        "/etc/shadow.pdf"):
            with self.subTest(name=hostile):
                path = attachment_upload_path(instance, hostile)
                self.assertTrue(path.startswith("tenant-7/"))
                self.assertNotIn("..", path)
                self.assertEqual(path.count("/"), 1)


class AttachmentValidationTests(SimpleTestCase):
    """§61: extension, size and MIME validation."""

    def test_an_allowed_type_with_matching_content_passes(self):
        extension, content_type = validate_attachment(upload())
        self.assertEqual(extension, ".pdf")
        self.assertEqual(content_type, "application/pdf")

    def test_a_disallowed_extension_is_refused(self):
        for name in ("evil.exe", "script.js", "shell.sh", "archive.zip", "noext"):
            with self.subTest(name=name):
                with self.assertRaises(ValidationError):
                    validate_attachment(upload(name, PDF_BYTES))

    def test_content_must_match_the_extension(self):
        """The whole point of sniffing: `report.pdf` can be anything at all, and
        the browser's declared Content-Type is supplied by the client."""
        with self.assertRaises(ValidationError):
            validate_attachment(
                upload("report.pdf", b"MZ\x90\x00 this is a windows executable",
                       content_type="application/pdf")
            )

    def test_a_renamed_executable_claiming_to_be_a_png_is_refused(self):
        with self.assertRaises(ValidationError):
            validate_attachment(
                upload("photo.png", b"MZ\x90\x00", content_type="image/png")
            )

    def test_an_oversized_file_is_refused(self):
        with override_settings(MEDICAL_ATTACHMENT_MAX_BYTES=100):
            with self.assertRaises(ValidationError):
                validate_attachment(upload("big.pdf", PDF_BYTES + b"x" * 200))

    def test_an_empty_file_is_refused(self):
        with self.assertRaises(ValidationError):
            validate_attachment(upload("empty.pdf", b""))

    def test_validation_leaves_the_file_readable(self):
        """It reads the head to sniff and the whole file to hash, so it must
        rewind — otherwise the upload is saved truncated or empty."""
        uploaded = upload()
        validate_attachment(uploaded)
        checksum(uploaded)
        uploaded.seek(0)
        self.assertEqual(uploaded.read(), PDF_BYTES)

    def test_the_checksum_is_the_sha256_of_the_content(self):
        self.assertEqual(checksum(upload()), hashlib.sha256(PDF_BYTES).hexdigest())
