"""The public logo and cover of the group and of each clinic.

Separate from `Branch.logo`, which is the printed letterhead's and unchanged.
These two are what the public page shows, so they follow an approval rule
(docs/15, D8):

* the group's own images are the Owner's, live at once;
* a clinic's images uploaded by the Owner are live at once;
* a clinic's images uploaded by its Admin wait in `pending_public_*` and reach
  the public page only when the Owner approves them.

Only the *approved* file is ever put in a public response. Files get random
names, so a pending image's address is not guessable from anything public.
"""

import uuid
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.utils import timezone
from PIL import Image, UnidentifiedImageError

KINDS = ("logo", "cover")

#: What is accepted, and how big. SVG is refused on purpose: it can carry script.
ALLOWED_FORMATS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
MAX_BYTES = {"logo": 1 * 1024 * 1024, "cover": 3 * 1024 * 1024}
MAX_SIDE = 4000


def _random_name(prefix, filename):
    extension = Path(filename).suffix.lower()
    return f"public/{prefix}/{uuid.uuid4().hex}{extension}"


def group_upload_path(instance, filename):
    return _random_name("group", filename)


def branch_upload_path(instance, filename):
    return _random_name("branch", filename)


def pending_upload_path(instance, filename):
    return _random_name("pending", filename)


def validate_image(upload, kind):
    """Refuse anything that is not a real, reasonably sized JPEG/PNG/WebP.

    The declared content type and the file name are never trusted: the bytes
    are opened and their real format is what counts.
    """
    if kind not in KINDS:
        raise ValidationError("نوع الصورة غير معروف.")
    if upload.size > MAX_BYTES[kind]:
        limit = MAX_BYTES[kind] // (1024 * 1024)
        raise ValidationError(f"حجم الصورة أكبر من {limit} ميجابايت.")
    try:
        upload.seek(0)
        with Image.open(upload) as image:
            image.verify()
            image_format = image.format
        upload.seek(0)
        with Image.open(upload) as image:
            width, height = image.size
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise ValidationError("الملف ليس صورة صالحة.")
    finally:
        upload.seek(0)
    if image_format not in ALLOWED_FORMATS:
        raise ValidationError("الصيغ المسموحة: JPG أو PNG أو WebP.")
    if max(width, height) > MAX_SIDE:
        raise ValidationError(f"أبعاد الصورة كبيرة (الحد {MAX_SIDE} بكسل).")
    # The stored name's extension follows the real format, not the uploaded name.
    upload.name = f"upload{ALLOWED_FORMATS[image_format]}"
    return upload


def url_of(file_field):
    """The address of a stored image, or None."""
    return file_field.url if file_field else None


def delete_file(file_field):
    if file_field:
        file_field.delete(save=False)


def approve_branch(branch, reviewer):
    """Make the branch's pending images the public ones. Returns what changed."""
    changed = []
    for kind in KINDS:
        pending = getattr(branch, f"pending_public_{kind}")
        if not pending:
            continue
        # Read and closed before anything is deleted: an open handle blocks the
        # delete on Windows.
        with pending.open("rb") as handle:
            content = ContentFile(handle.read())
        delete_file(getattr(branch, f"public_{kind}"))
        # Re-saved under the public path: the pending name stays private.
        getattr(branch, f"public_{kind}").save(Path(pending.name).name, content, save=False)
        delete_file(pending)
        setattr(branch, f"pending_public_{kind}", None)
        changed.append(kind)
    branch.media_status = ""
    branch.media_review_note = ""
    branch.media_reviewed_by = reviewer
    branch.media_reviewed_at = timezone.now()
    branch.save()
    return changed


def reject_branch(branch, reviewer, note=""):
    """Throw the pending images away and tell the Admin why."""
    for kind in KINDS:
        delete_file(getattr(branch, f"pending_public_{kind}"))
        setattr(branch, f"pending_public_{kind}", None)
    branch.media_status = "rejected"
    branch.media_review_note = (note or "").strip()[:300]
    branch.media_reviewed_by = reviewer
    branch.media_reviewed_at = timezone.now()
    branch.save()
