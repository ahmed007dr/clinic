from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib import messages
from django.urls import reverse
from django.contrib.auth.decorators import login_required, user_passes_test

from .forms import LoginForm, UserForm, UserSettingsForm
from branches.models import Branch
from audit.models import AuditLog
from accounts.roles import is_owner

User = get_user_model()


def user_login(request):
    if request.user.is_authenticated:
        return redirect('dashboard:dashboard')

    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                AuditLog.objects.create(
                    tenant=user.tenant,
                    user=user,
                    action="login",
                    description="User logged in",
                    ip_address=request.META.get("REMOTE_ADDR"),
                    user_agent=request.META.get("HTTP_USER_AGENT"),
                )
                #next_url = request.GET.get('next', 'dashboard')
                next_url = request.GET.get('next', reverse("dashboard:dashboard"))

                return redirect(next_url)
            else:
                messages.error(request, 'اسم المستخدم أو كلمة المرور غير صحيحة')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = LoginForm()

    context = {
        'form': form,
    }
    return render(request, 'accounts/login.html', context)


@login_required
def user_logout(request):
    AuditLog.objects.create(
        tenant=request.user.tenant,
        user=request.user,
        action="logout",
        description="User logged out",
        ip_address=request.META.get("REMOTE_ADDR"),
        user_agent=request.META.get("HTTP_USER_AGENT"),
    )
    logout(request)
    return redirect('accounts:login')


@login_required
@user_passes_test(is_owner)
def user_create(request):
    if request.method == 'POST':
        form = UserForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.tenant = request.user.tenant
            user.save()
            messages.success(request, f'تم إنشاء المستخدم {user.username} بنجاح')
            return redirect('accounts:user_list')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = UserForm()

    context = {
        'form': form,
    }
    return render(request, 'accounts/user_create.html', context)


@login_required
@user_passes_test(is_owner)
def user_list(request):
    users = User.objects.all()
    context = {
        'users': users,
    }
    return render(request, 'accounts/user_list.html', context)


@login_required
@user_passes_test(is_owner)
def user_update(request, uuid):
    user = get_object_or_404(User, uuid=uuid)
    if request.method == 'POST':
        form = UserForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, f'تم تعديل المستخدم {user.username} بنجاح')
            return redirect('accounts:user_list')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = UserForm(instance=user)

    context = {
        'form': form,
    }
    return render(request, 'accounts/user_update.html', context)


@login_required
@user_passes_test(is_owner)
def user_delete(request, uuid):
    user = get_object_or_404(User, uuid=uuid)
    if request.method == 'POST':
        user.delete()
        messages.success(request, 'تم حذف المستخدم بنجاح')
        return redirect('accounts:user_list')
    context = {
        'user': user,
    }
    return render(request, 'accounts/user_delete.html', context)


@login_required
def user_settings(request):
    if request.method == 'POST':
        form = UserSettingsForm(request.POST, instance=request.user)
        # Disabled *before* validation. Disabling after is_valid() came too
        # late — the posted role had already been accepted — which let any
        # user promote themselves from this form. A disabled field takes
        # its value from the instance and ignores what was posted.
        if not is_owner(request.user):
            form.fields['role'].disabled = True
            form.fields['branch'].disabled = True
        if form.is_valid():
            form.save()
            messages.success(request, 'تم تحديث الإعدادات بنجاح')
            return redirect('dashboard:dashboard')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = UserSettingsForm(instance=request.user)
        if not is_owner(request.user):
            form.fields['role'].disabled = True
            form.fields['branch'].disabled = True

    context = {
        'form': form,
    }
    return render(request, 'accounts/settings.html', context)
