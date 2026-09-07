from django.shortcuts import render
from .models import AuditLog
from django.contrib.auth.decorators import login_required, user_passes_test

@login_required
@user_passes_test(lambda u: u.role.name == 'Admin' if u.role else False)
def audit_list(request):
    audit_logs = AuditLog.objects.all().order_by('-created_at')
    context = {
        'audit_logs': audit_logs,
    }
    return render(request, 'audit/list.html', context)