"""What a clinic's printed sheets look like, from its own settings.

The clinic's Admin or the Owner sets the letterhead — logo, the name and
lines under it, contact details, footer, one accent colour — and what the
patient intake form asks for (api/views/print_settings.py). Every printed
page (the intake form, prescriptions) reads it through `letterhead()`, so a
change shows on all of them at once.
"""

import re

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
