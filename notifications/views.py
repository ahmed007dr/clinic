from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.core.paginator import Paginator
from .models import Notification
from accounts.roles import is_front_desk

def is_reception_or_admin(user):
    return is_front_desk(user)

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
def notification_mark_read(request, uuid):
    # get_object_or_404, not .get(): a notification that does not exist — or
    # belongs to someone else — was raising DoesNotExist and returning a 500
    # instead of a 404. The user filter already prevents reading another
    # user's notification; this makes the refusal an ordinary 404.
    notification = get_object_or_404(Notification, uuid=uuid, user=request.user)
    notification.is_read = True
    notification.save()
    messages.success(request, 'تم تحديد الإشعار كمقروء')
    return redirect('notifications:notification_list')