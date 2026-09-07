import threading
from django.utils.deprecation import MiddlewareMixin
from .models import AuditLog

_thread_locals = threading.local()


def get_current_request():
    return getattr(_thread_locals, "request", None)


class ThreadLocalMiddleware:
    """ Middleware لحفظ request لكل thread، مع مسحه دائمًا بعد انتهاء الطلب.
    بدون المسح في finally، أي عملية save() تحدث على نفس الـ thread خارج
    سياق طلب فعلي (مثل: طلب لاحق تتعامل معه Passenger على نفس الـ worker
    thread قبل أي طلب جديد، أو اختبارات تعمل على نفس الـ thread) كانت
    ستُنسب خطأً إلى مستخدم الطلب السابق في AuditLog. """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _thread_locals.request = request
        try:
            return self.get_response(request)
        finally:
            _thread_locals.request = None


class AuditMiddleware(MiddlewareMixin):
    """ Middleware يسجل دخول/خروج عبر Django admin فقط.
    تسجيل الدخول/الخروج الفعلي للتطبيق (accounts:login/logout) يتم
    تسجيله مباشرة من accounts.views، لأن المستخدم لا يكون
    is_authenticated بعد أثناء معالجة طلب تسجيل الدخول نفسه. """
    def process_view(self, request, view_func, view_args, view_kwargs):
        if request.user.is_authenticated:
            if request.path == "/admin/login/":
                AuditLog.objects.create(
                    user=request.user,
                    action="login",
                    description="User logged in",
                    ip_address=request.META.get("REMOTE_ADDR"),
                    user_agent=request.META.get("HTTP_USER_AGENT"),
                )
            elif request.path == "/admin/logout/":
                AuditLog.objects.create(
                    user=request.user,
                    action="logout",
                    description="User logged out",
                    ip_address=request.META.get("REMOTE_ADDR"),
                    user_agent=request.META.get("HTTP_USER_AGENT"),
                )
