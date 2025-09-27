from django.shortcuts import render, redirect
from .forms import AppointmentForm
from .models import Appointment
from django.conf import settings
from django.contrib import messages
from django.urls import reverse
from django.contrib.auth.decorators import login_required

@login_required
def appointment_create(request):
    if request.method == 'POST':
        form = AppointmentForm(request.POST)
        if form.is_valid():
            appointment = form.save(commit=False)
            appointment.created_by = request.user
            appointment.save()
            messages.success(request, f'تم حجز الموعد بنجاح (رقم التذكرة: {appointment.id})')
            return redirect('appointment_list')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = AppointmentForm()

    context = {
        'form': form,
        'clinic_name': getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'appointments/create.html', context)

@login_required
def appointment_list(request):
    appointments = Appointment.objects.filter(status__name='Scheduled').order_by('scheduled_date')
    context = {
        'appointments': appointments,
        'clinic_name': getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'appointments/list.html', context)