from django.shortcuts import render
from .models import AuditLog
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from accounts.roles import is_owner

LIMIT = 500

@login_required
def audit_list(request):
    """The change log — the group owner's. Anyone else signed in gets a plain 403."""
    if not is_owner(request.user):
        raise PermissionDenied('سجل التغييرات مقصور على مالك المجموعة.')
    # The newest entries only: the log grows with every change anyone makes,
    # and rendering all of it in one page is what an old clinic would feel.
    audit_logs = AuditLog.objects.select_related('user').order_by('-created_at')[:LIMIT]
    context = {
        'audit_logs': audit_logs,
        'limit': LIMIT,
    }
    return render(request, 'audit/list.html', context)