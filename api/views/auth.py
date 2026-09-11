"""Signing in, signing out, and knowing who you are.

Session authentication, not tokens — and the reason is structural rather than a
preference.

`TenantMiddleware` binds the tenant, and therefore the PostgreSQL row-level
security context, from `request.user`. Middleware runs *before* the view. DRF
token authentication runs *inside* the view, so at the moment the tenant is
bound `request.user` is still anonymous: nothing is bound, and every query in
the request returns nothing under RLS. A token API would have to re-implement
tenant binding, and re-implementing the one control that keeps clinics apart to
save a cookie is a bad trade.

Sessions also avoid storing a bearer credential in JavaScript reach: the cookie
is `HttpOnly`, so a cross-site scripting bug cannot read it, and CSRF is handled
by Django's own token rather than by hand.
"""

from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.debug import sensitive_post_parameters
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from accounts.roles import account_is_usable
from api.permissions import IsClinicMember
from tenants.context import tenant_context
from platform_admin.permissions import is_platform_staff
from api.serializers.accounts import (
    CurrentUserSerializer,
    LoginSerializer,
    PasswordChangeSerializer,
)


def platform_payload(user):
    return {"username": user.username, "email": user.email}


class LoginRateThrottle(AnonRateThrottle):
    """Password guessing is the one unauthenticated write this API exposes."""

    scope = "login"


@method_decorator(ensure_csrf_cookie, name="dispatch")
class SessionView(APIView):
    """`GET /api/auth/session/` — the SPA's first call.

    Does two jobs at once. It reports whether there is a live session, so the
    app can route to the login screen or straight to the dashboard without a
    flash of the wrong one. And `ensure_csrf_cookie` guarantees the `csrftoken`
    cookie exists before any write is attempted — without this the very first
    POST of a fresh browser session fails CSRF validation, which looks like a
    broken login and is really a missing handshake.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        get_token(request)  # force the cookie even if the view is cached
        user = request.user
        if not user.is_authenticated:
            return Response({"authenticated": False, "user": None})
        if getattr(user, "tenant_id", None) is None:
            # Platform staff get the owner portal and nothing else: `user` stays
            # None, so every clinic screen and endpoint still refuses them.
            if is_platform_staff(user):
                return Response({
                    "authenticated": True, "user": None,
                    "platform_user": platform_payload(user),
                })
            return Response({"authenticated": True, "user": None})
        return Response(
            {"authenticated": True, "user": CurrentUserSerializer(user).data}
        )


@method_decorator(sensitive_post_parameters("password"), name="dispatch")
class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = authenticate(
            request,
            username=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            # One message for "no such account" and "wrong password". Telling
            # them apart turns the login form into a directory of who works
            # here.
            return Response(
                {"detail": "البريد الإلكتروني أو كلمة المرور غير صحيحة."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if getattr(user, "tenant_id", None) is None:
            if is_platform_staff(user):
                login(request, user)
                return Response({"user": None, "platform_user": platform_payload(user)})
            return Response(
                {"detail": "هذا الحساب غير مرتبط بعيادة."},
                status=status.HTTP_403_FORBIDDEN,
            )
        tenant = user.tenant
        with tenant_context(tenant):
            clinic_stopped = not account_is_usable(user)
        if clinic_stopped:
            return Response(
                {"detail": "تم إيقاف الفرع الذي تعمل به. تواصل مع صاحب المجمع."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not tenant.is_usable:
            # A suspended clinic must not be able to keep recording work; the
            # refusal is at sign-in so it is unambiguous rather than surfacing
            # as scattered failures later.
            return Response(
                {"detail": "اشتراك العيادة غير نشط. يرجى التواصل مع الدعم."},
                status=status.HTTP_403_FORBIDDEN,
            )

        login(request, user)
        return Response({"user": CurrentUserSerializer(user).data})


class LogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordChangeView(APIView):
    permission_classes = [IsClinicMember]

    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(serializer.validated_data["current_password"]):
            return Response(
                {"current_password": ["كلمة المرور الحالية غير صحيحة."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        # Without this the user is signed out of the tab they just used, because
        # changing a password rotates the session hash.
        update_session_auth_hash(request, user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ActiveBranchView(APIView):
    """`POST {branch: <uuid>}` — a doctor linked to several clinics chooses
    which one they are looking at. Every list, figure and screen follows it
    (accounts.roles.current_branch_id). Only clinics the Owner has linked the
    doctor to are accepted; anything else is refused, not ignored."""

    permission_classes = [IsClinicMember]

    def post(self, request):
        from accounts.middleware import SESSION_KEY
        from accounts.roles import doctor_branch_ids
        from branches.models import Branch

        branch = Branch.objects.filter(uuid=request.data.get("branch")).first()
        if branch is None or branch.pk not in doctor_branch_ids(request.user):
            return Response(
                {"detail": "هذا الفرع غير مرتبط بحسابك."}, status=status.HTTP_400_BAD_REQUEST
            )
        request.session[SESSION_KEY] = branch.pk
        request.user.active_branch_id = branch.pk
        return Response({"user": CurrentUserSerializer(request.user).data})
