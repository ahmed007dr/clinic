from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.lib import colors
import io
from django.template.loader import render_to_string

def export_pdf(template_name, context, filename, rtl=True):
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    
    # تسجيل خط عربي
    try:
        pdfmetrics.registerFont(TTFont('Cairo', 'static/fonts/sourcesanspro/Cairo-Regular.ttf'))
    except Exception as e:
        print(f"Error loading font: {e}")
        raise
    
    pdf.setFont('Cairo', 12)
    pdf.setTitle(filename)

    # تحويل التمبليت إلى نص
    html_content = render_to_string(template_name, context)
    
    # تقسيم النص إلى أسطر للعرض في PDF
    y = 750
    lines = html_content.split('\n')
    for line in lines:
        line = line.strip()
        if line:
            # تنظيف النص من الوسوم HTML البسيطة
            clean_line = line.replace('<p>', '').replace('</p>', '').replace('<h2>', '').replace('</h2>', '').replace('<h3>', '').replace('</h3>', '').replace('<li>', '').replace('</li>', '')[:100]
            if rtl:
                pdf.drawRightString(500, y, clean_line)
            else:
                pdf.drawString(50, y, clean_line)
            y -= 20
            if y < 50:
                pdf.showPage()
                y = 750
                pdf.setFont('Cairo', 12)
    
    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()