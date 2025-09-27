from django.shortcuts import render, redirect
from .forms import PatientForm
from django.conf import settings
from django.contrib import messages
from django.urls import reverse

def patient_create(request):
    if not request.user.is_authenticated:
        return redirect('login')
    
    if request.method == 'POST':
        form = PatientForm(request.POST, request.FILES)
        if form.is_valid():
            patient = form.save()
            messages.success(request, f'تم تسجيل المريض {patient.name} بنجاح')
            return redirect('appointment_create')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = PatientForm()

    context = {
        'form': form,
        'clinic_name': getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'patients/create.html', context)