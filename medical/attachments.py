"""Storage and validation for medical attachments — doc/readme.md §61.

§61 asks for authorization, tenant validation, clinic validation, MIME
validation, extension validation, a size limit and secure storage. Authorization
and the tenant/branch checks live in the view and the scoped manager; everything
else is here.

The central decision is that these files are **not** stored under `MEDIA_ROOT`.
Anything in `MEDIA_ROOT` is a candidate for the web server to serve directly,
and a file served by the web server has bypassed every permission check the
application makes. That is not hypothetical here: with `DEBUG = True` Django
itself serves `MEDIA_ROOT` with no authentication at all, so a patient's scan
would be readable by anyone who knew or guessed the URL. Storing them elsewhere
means a misconfigured server cannot expose them even by accident.

The storage is also given no `base_url`, so `attachment.file.url` raises instead
of returning a path. A template that reaches for it fails loudly rather than
rendering a link that leaks — the failure mode we want is a broken page, not a
quiet disclosure.
"""

import hashlib
import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage

# Kept deliberately short. Every entry is something a clinic genuinely attaches
# to a record, and each one has a magic number we can check, which is what makes
# the content check below possible without a libmagic dependency.
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}

# Leading bytes that must be present for the declared extension. The browser's
# Content-Type is not consulted: it is supplied by the client and a renamed
# executable will happily claim to be a PNG.
MAGIC_NUMBERS = {
    ".pdf": [b"%PDF-"],
    ".png": [b"\x89PNG\r\n\x1a\n"],
    ".jpg": [b"\xff\xd8\xff"],
    ".jpeg": [b"\xff\xd8\xff"],
    # RIFF....WEBP — the four size bytes in between are skipped.
    ".webp": [b"RIFF"],
}

CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


class PrivateAttachmentStorage(FileSystemStorage):
    """A storage that refuses to produce a URL at all.

    Passing `base_url=None` to FileSystemStorage does **not** do this — `None`
    means "use the default", and the default is `MEDIA_URL`. A storage built
    that way returns `/media/tenant-1/<uuid>.pdf` from `.url()`, which is
    precisely the kind of path this design exists to never emit. Overriding the
    method is the only way to guarantee it.

    The failure mode we want from a template that reaches for `.url` is a broken
    page, not a quietly rendered link to a patient's scan.
    """

    def url(self, name):
        raise ValueError(
            "Medical attachments have no public URL by design; "
            "serve them through medical.views.attachment_download."
        )


def attachment_storage():
    """A storage rooted outside MEDIA_ROOT, which cannot produce a URL.

    Built per call rather than at import so that `override_settings` works in
    tests — a module-level instance would capture the location once and ignore
    every later change.
    """
    return PrivateAttachmentStorage(location=str(settings.MEDICAL_ATTACHMENTS_ROOT))


def attachment_upload_path(instance, filename):
    """Where the file lands on disk.

    The uploaded name is never used. It is attacker-controlled, so it can carry
    path separators, be 300 characters long, collide with an existing file, or
    simply reveal something about the patient in a directory listing. A random
    name avoids all of that, and the original is kept in the database column
    where it is data rather than a filesystem path.

    Partitioned by tenant so that a mistake in one clinic's directory cannot
    reach another's, and so a tenant's files can be exported or destroyed as a
    unit when offboarding.
    """
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        extension = ""
    return f"tenant-{instance.tenant_id}/{uuid.uuid4().hex}{extension}"


def validate_attachment(uploaded):
    """Extension, size and content checks — §61.

    Returns the detected extension and content type. Raises ValidationError with
    a message safe to show a user: §62 forbids leaking filesystem paths or
    internal detail into responses.
    """
    extension = Path(uploaded.name or "").suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        allowed = "، ".join(sorted(e.lstrip(".") for e in ALLOWED_EXTENSIONS))
        raise ValidationError(f"نوع الملف غير مسموح. المسموح: {allowed}")

    limit = settings.MEDICAL_ATTACHMENT_MAX_BYTES
    if uploaded.size > limit:
        raise ValidationError(
            f"حجم الملف يتجاوز الحد المسموح ({limit // (1024 * 1024)} ميجابايت)"
        )
    if uploaded.size == 0:
        raise ValidationError("الملف فارغ")

    # Read the head rather than trusting the extension or the declared type.
    # Without this, `report.pdf` can be anything at all.
    position = uploaded.tell()
    uploaded.seek(0)
    head = uploaded.read(16)
    uploaded.seek(position)

    if not any(head.startswith(magic) for magic in MAGIC_NUMBERS[extension]):
        raise ValidationError("محتوى الملف لا يطابق نوعه")
    if extension == ".webp" and head[8:12] != b"WEBP":
        # RIFF is a container; only the WEBP form is accepted.
        raise ValidationError("محتوى الملف لا يطابق نوعه")

    return extension, CONTENT_TYPES[extension]


def checksum(uploaded):
    """SHA-256 of the upload, so a stored record can be shown to be the file
    that was uploaded. Medical records that change silently are the thing §66
    exists to prevent, and a hash is what makes silence detectable."""
    position = uploaded.tell()
    uploaded.seek(0)
    digest = hashlib.sha256()
    for chunk in iter(lambda: uploaded.read(64 * 1024), b""):
        digest.update(chunk)
    uploaded.seek(position)
    return digest.hexdigest()
