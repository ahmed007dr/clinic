"""PDF and Excel export.

The PDF side has to do three things before reportlab can draw Arabic at all,
and doing only some of them produces output that looks repaired while being
unreadable — see FE-016 and static/fonts/cairo/README.md.

1. Embed a font that has Arabic glyphs. reportlab embeds only what it is given,
   and its default Helvetica has none, so every Arabic character came out blank.
2. Shape the letters. Arabic letters change form by position (initial, medial,
   final, isolated); reportlab applies no OpenType GSUB, so unshaped text
   renders as disconnected stumps.
3. Reorder for direction. Arabic runs right to left; without the bidi algorithm
   the shaped letters are drawn in reverse.

Excel needs none of this — openpyxl embeds no fonts and the spreadsheet
application handles direction and shaping itself.
"""

import re
from datetime import datetime
from io import BytesIO
from pathlib import Path

import openpyxl
from arabic_reshaper import ArabicReshaper
from bidi.algorithm import get_display
from django.conf import settings
from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

ARABIC_FONT = "Cairo"
ARABIC_FONT_PATH = Path(settings.BASE_DIR) / "static" / "fonts" / "cairo" / "Cairo.ttf"

# Arabic, Arabic Supplement, Arabic Extended-A, and the two presentation-form
# blocks the reshaper emits into.
_ARABIC_CHARS = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")

# use_unshaped_instead_of_isolated is load-bearing, not a tweak. By default the
# reshaper maps isolated letters onto Arabic Presentation Forms-B, and Cairo —
# like most modern fonts — implements isolated forms through the base codepoint
# plus GSUB instead of duplicating them there. Seventeen codepoints therefore had
# no glyph and rendered blank. This setting leaves them as their base codepoints.
_reshaper = ArabicReshaper(configuration={"use_unshaped_instead_of_isolated": True})


def register_arabic_font():
    """Idempotent: reportlab keeps a process-global font registry, and these
    exports are called per request."""
    if ARABIC_FONT not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(ARABIC_FONT, str(ARABIC_FONT_PATH)))
    return ARABIC_FONT


def rtl(value):
    """Shape and reorder a value so reportlab draws readable Arabic.

    Left alone when there is no Arabic in it, so receipt numbers, amounts and
    dates pass through untouched rather than being run through a bidi pass that
    could only reorder them.
    """
    text = "" if value is None else str(value)
    if not _ARABIC_CHARS.search(text):
        return text
    return get_display(_reshaper.reshape(text))


def arabic_table_style():
    """The table's styling, as a separate function so a test can assert that
    every FONTNAME in it is the Arabic face.

    That assertion is not pedantry. Cairo is the only embedded font that has
    Arabic glyphs, and the title alone is enough to embed it — so setting the
    header row back to Helvetica-Bold (as this code originally did) leaves a
    document that still *contains* Cairo while every table cell renders blank.
    Checking the produced bytes cannot distinguish those two cases; checking the
    style can.
    """
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        # One font throughout, header included. The header still reads as a
        # header from its fill and larger size.
        ("FONTNAME", (0, 0), (-1, -1), ARABIC_FONT),
        ("FONTSIZE", (0, 0), (-1, 0), 14),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
        ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
    ])


def export_pdf(data, headers, title, filename):
    register_arabic_font()

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    base = getSampleStyleSheet()

    # The whole application is `<html lang="ar" dir="rtl">`, so the document is
    # laid out to match: right-aligned body, and header cells in RTL order.
    title_style = ParagraphStyle(
        "RtlTitle", parent=base["Title"], fontName=ARABIC_FONT, alignment=TA_CENTER
    )
    meta_style = ParagraphStyle(
        "RtlMeta", parent=base["Normal"], fontName=ARABIC_FONT, alignment=TA_RIGHT
    )

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    elements = [
        Paragraph(rtl(title), title_style),
        Paragraph(rtl(f"تاريخ الإنشاء: {stamp}"), meta_style),
    ]

    # Columns are reversed so the first header sits on the right, which is where
    # an Arabic reader starts. Applied to header and body together, so a cell
    # never parts company with its column.
    table_data = [[rtl(cell) for cell in reversed(row)] for row in [headers] + list(data)]

    table = Table(table_data)
    table.setStyle(arabic_table_style())
    elements.append(table)

    doc.build(elements)
    buffer.seek(0)
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}.pdf"'
    response.write(buffer.getvalue())
    buffer.close()
    return response

def export_excel(data, headers, title, filename):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title
    
    # إضافة العنوان
    ws.append([title])
    ws.append([f"تاريخ الإنشاء: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
    ws.append([])
    
    # إضافة رأس الجدول
    ws.append(headers)
    
    # إضافة البيانات
    for row in data:
        ws.append(row)
    
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{filename}.xlsx"'
    response.write(buffer.getvalue())
    buffer.close()
    return response