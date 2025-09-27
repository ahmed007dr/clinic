from django.shortcuts import render
from .models import AuditLog
from django.conf import settings
from django.contrib.auth.decorators import login_required

@login_required
def audit_list(request):
    audit_logs = AuditLog.objects.all().order_by('-created_at')
    context = {
        'audit_logs': audit_logs,
        'clinic_name': getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'audit/list.html', context)