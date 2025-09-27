from django.shortcuts import render, redirect, get_object_or_404
from .models import Notification
from django.conf import settings
from django.contrib import messages
from django.urls import reverse
from django.contrib.auth.decorators import login_required

@login_required
def notification_list(request):
    notifications = Notification.objects.filter(user=request.user).order_by('-created_at')
    context = {
        'notifications': notifications,
        'clinic_name': getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'notifications/list.html', context)

@login_required
def notification_mark_read(request, pk):
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    if request.method == 'POST':
        notification.is_read = True
        notification.save()
        messages.success(request, 'تم تحديد الإشعار كمقروء')
        return redirect('notification_list')
    context = {
        'notification': notification,
        'clinic_name': getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'notifications/mark_read.html', context)