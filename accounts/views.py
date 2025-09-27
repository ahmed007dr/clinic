from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib import messages
from django.urls import reverse
from django.contrib.auth.decorators import login_required, user_passes_test
from django.conf import settings

from .forms import LoginForm, UserForm, UserSettingsForm
from branches.models import Branch

User = get_user_model()


def user_login(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                next_url = request.GET.get('next', 'dashboard')
                return redirect(next_url)
            else:
                messages.error(request, 'اسم المستخدم أو كلمة المرور غير صحيحة')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = LoginForm()

    context = {
        'form': form,
        'clinic_name': getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'accounts/login.html', context)


@login_required
def user_logout(request):
    logout(request)
    return redirect('login')


@login_required
@user_passes_test(lambda u: u.role and u.role.name == 'Admin')
def user_create(request):
    if request.method == 'POST':
        form = UserForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f'تم إنشاء المستخدم {user.username} بنجاح')
            return redirect('user_list')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = UserForm()

    context = {
        'form': form,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'accounts/user_create.html', context)


@login_required
@user_passes_test(lambda u: u.role and u.role.name == 'Admin')
def user_list(request):
    users = User.objects.all()
    context = {
        'users': users,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'accounts/user_list.html', context)


@login_required
@user_passes_test(lambda u: u.role and u.role.name == 'Admin')
def user_update(request, pk):
    user = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        form = UserForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, f'تم تعديل المستخدم {user.username} بنجاح')
            return redirect('user_list')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = UserForm(instance=user)

    context = {
        'form': form,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'accounts/user_update.html', context)


@login_required
@user_passes_test(lambda u: u.role and u.role.name == 'Admin')
def user_delete(request, pk):
    user = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        user.delete()
        messages.success(request, 'تم حذف المستخدم بنجاح')
        return redirect('user_list')
    context = {
        'user': user,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'accounts/user_delete.html', context)


@login_required
def user_settings(request):
    if request.method == 'POST':
        form = UserSettingsForm(request.POST, instance=request.user)
        if form.is_valid():
            if request.user.role and request.user.role.name != 'Admin':
                form.fields['role'].disabled = True
                form.fields['branch'].disabled = True
            form.save()
            messages.success(request, 'تم تحديث الإعدادات بنجاح')
            return redirect('dashboard')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = UserSettingsForm(instance=request.user)
        if request.user.role and request.user.role.name != 'Admin':
            form.fields['role'].disabled = True
            form.fields['branch'].disabled = True

    context = {
        'form': form,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'accounts/settings.html', context)
