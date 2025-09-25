import threading
from django.utils.deprecation import MiddlewareMixin
from .models import AuditLog

_thread_locals = threading.local()


def get_current_request():
    return getattr(_thread_locals, "request", None)


class ThreadLocalMiddleware(MiddlewareMixin):
    """ Middleware لحفظ request لكل thread """
    def process_request(self, request):
        _thread_locals.request = request


class AuditMiddleware(MiddlewareMixin):
    """ Middleware يسجل دخول/خروج """
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
