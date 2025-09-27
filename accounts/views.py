from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from .forms import LoginForm
from django.conf import settings
from django.contrib import messages

def user_login(request):
    if request.user.is_authenticated:
        return redirect('appointment_list')
    
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                return redirect('appointment_list')
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

def user_logout(request):
    logout(request)
    return redirect('login')