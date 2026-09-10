from django.shortcuts import render
from .models import AuditLog
from django.contrib.auth.decorators import login_required, user_passes_test
from accounts.roles import is_owner

@login_required
@user_passes_test(is_owner)
def audit_list(request):
    audit_logs = AuditLog.objects.all().order_by('-created_at')
    context = {
        'audit_logs': audit_logs,
    }
    return render(request, 'audit/list.html', context)