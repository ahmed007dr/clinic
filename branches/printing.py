"""What a clinic's printed sheets look like, from its own settings.

The clinic's Admin or the Owner sets the letterhead — logo, the name and
lines under it, contact details, footer, one accent colour — and what the
patient intake form asks for (api/views/print_settings.py). Every printed
page (the intake form, prescriptions) reads it through `letterhead()`, so a
change shows on all of them at once.
"""

import re
from urllib.parse import urlparse

from django.conf import settings

DEFAULT_ACCENT = "#0e6e63"
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

#: The intake form's standard sections, in print order: key → heading.
INTAKE_SECTIONS = {
    "personal": "البيانات الشخصية",
    "contact": "بيانات التواصل",
    "emergency": "شخص للطوارئ",
    "visit": "سبب الزيارة",
    "medical": "التاريخ المرضي",
    "allergies": "الحساسية",
    "medications": "الأدوية الحالية",
    "consent": "الإقرار والتوقيع",
}


def letterhead(branch, request=None):
    """The header/footer of a printed sheet for `branch` (may be None)."""
    name = getattr(branch, "name", None) or getattr(settings, "CLINIC_NAME", "")
    logo_url = None
    if branch is not None and branch.logo:
        logo_url = branch.logo.url
        if request is not None:
            logo_url = request.build_absolute_uri(logo_url)
    accent = getattr(branch, "print_accent_color", "") or DEFAULT_ACCENT
    return {
        "title": getattr(branch, "print_header_title", "") or name,
        "subtitle": getattr(branch, "print_header_subtitle", ""),
        "address": getattr(branch, "address", "") or "",
        "phone": getattr(branch, "phone", "") or "",
        "email": getattr(branch, "email", "") or "",
        "footer": getattr(branch, "footer_text", "") or "",
        # Validated again here: it is written into a <style> block.
        "accent": accent if HEX.match(accent) else DEFAULT_ACCENT,
        "logo_url": logo_url,
        "logo_in_footer": getattr(branch, "print_logo_in_footer", False),
        # Only the links the clinic filled in (link_items drops the rest).
        "links": link_items(getattr(branch, "print_links", None)),
    }


def intake_layout(branch):
    """The intake form's title, intro, sections and extra lines."""
    chosen = [key for key in (getattr(branch, "intake_sections", None) or []) if key in INTAKE_SECTIONS]
    return {
        "title": getattr(branch, "intake_form_title", "") or "استمارة تسجيل مريض",
        "intro": getattr(branch, "intake_form_intro", ""),
        "consent": getattr(branch, "intake_consent_text", "")
        or "أقر بأن البيانات المذكورة أعلاه صحيحة، وأوافق على تلقي العلاج وعلى حفظ بياناتي الطبية لدى العيادة.",
        # Nothing chosen yet means everything: a new clinic prints a full form.
        "sections": chosen or list(INTAKE_SECTIONS),
        "extra_fields": [str(label)[:80] for label in (getattr(branch, "intake_extra_fields", None) or [])][:20],
    }


# ---------------------------------------------------------------- links

#: Every kind of link a clinic or a doctor may show, in display order:
#: key -> Arabic label. WhatsApp is a phone number; the rest are web addresses.
LINK_KINDS = {
    "whatsapp": "واتساب",
    "facebook": "فيسبوك",
    "instagram": "إنستجرام",
    "tiktok": "تيك توك",
    "youtube": "يوتيوب",
    "x": "إكس",
    "website": "الموقع",
    "maps": "الموقع على الخريطة",
}
MAX_URL = 200


class LinkError(ValueError):
    """The message names the link and is for the user."""


def clean_links(raw):
    """Validate a {kind: value} mapping; drop empty values. Only http(s)
    addresses are accepted — a printed or portal link must never be able to
    carry `javascript:` or anything else a browser would execute."""
    if raw in (None, ""):
        return {}
    if not isinstance(raw, dict):
        raise LinkError("الروابط غير صالحة.")
    cleaned = {}
    for kind, value in raw.items():
        if kind not in LINK_KINDS:
            raise LinkError(f"نوع رابط غير معروف: {kind}")
        value = str(value or "").strip()
        if not value:
            continue
        label = LINK_KINDS[kind]
        if kind == "whatsapp":
            digits = re.sub(r"[\s\-()+]", "", value)
            if not digits.isdigit() or not 8 <= len(digits) <= 15:
                raise LinkError(f"{label}: اكتب رقم الهاتف بالأرقام مع كود الدولة، مثل 201001234567.")
            cleaned[kind] = digits
            continue
        if len(value) > MAX_URL or " " in value:
            raise LinkError(f"{label}: الرابط غير صالح.")
        if not value.startswith(("http://", "https://")):
            value = "https://" + value
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https") or not parsed.netloc or "." not in parsed.netloc:
            raise LinkError(f"{label}: الرابط غير صالح.")
        cleaned[kind] = value
    return cleaned


def link_items(links):
    """[{kind, label, url, text}] in display order, for templates and the
    portal. `text` is what fits on paper: the address without its scheme."""
    items = []
    for kind, label in LINK_KINDS.items():
        value = (links or {}).get(kind)
        if not value:
            continue
        if kind == "whatsapp":
            items.append({"kind": kind, "label": label, "url": f"https://wa.me/{value}", "text": f"+{value}"})
        else:
            text = re.sub(r"^https?://(www\.)?", "", value).rstrip("/")
            items.append({"kind": kind, "label": label, "url": value, "text": text})
    return items


def clean_profile(raw):
    """A doctor's footer: a short line about them and their links."""
    if not isinstance(raw, dict):
        raise LinkError("البيانات غير صالحة.")
    tagline = str(raw.get("tagline") or "").strip()[:150]
    return {"tagline": tagline, "links": clean_links(raw.get("links"))}


def doctor_signature(employee):
    """What a doctor's prescriptions carry under their name — only what the
    clinic's Admin has approved (employees.Employee.public_profile)."""
    profile = getattr(employee, "public_profile", None) or {}
    items = link_items(profile.get("links"))
    tagline = profile.get("tagline", "")
    if not items and not tagline:
        return None
    return {"tagline": tagline, "links": items}
