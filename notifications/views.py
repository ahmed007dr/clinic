from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.core.paginator import Paginator
from .models import Notification

def is_reception_or_admin(user):
    return user.role.name in ['Reception', 'Admin'] if user.role else False

@login_required
@user_passes_test(is_reception_or_admin)
def notification_list(request):
    notifications = Notification.objects.filter(user=request.user).order_by('-created_at', '-serial_number')
    paginator = Paginator(notifications, 20)  # 20 إشعارًا لكل صفحة
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'notifications': page_obj,
        'page_obj': page_obj,
    }
    return render(request, 'notifications/list.html', context)

@login_required
@user_passes_test(is_reception_or_admin)
def notification_mark_read(request, pk):
    notification = Notification.objects.get(pk=pk, user=request.user)
    notification.is_read = True
    notification.save()
    messages.success(request, 'تم تحديد الإشعار كمقروء')
    return redirect('notifications:notification_list')