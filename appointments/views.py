from django.shortcuts import render, redirect, get_object_or_404
from .forms import AppointmentForm
from .models import Appointment
from branches.models import Branch
from django.conf import settings
from django.contrib import messages
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone

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

    branch = Branch.objects.first()
    context = {
        'form': form,
        'clinic_name': branch.name if branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': branch.logo.url if branch and branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': branch.footer_text if branch and branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'appointments/create.html', context)

@login_required
def appointment_list(request):
    appointments = Appointment.objects.all().order_by('scheduled_date')
    branch = Branch.objects.first()
    context = {
        'appointments': appointments,
        'clinic_name': branch.name if branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': branch.logo.url if branch and branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': branch.footer_text if branch and branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'appointments/list.html', context)

@login_required
def appointment_detail(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)
    branch = Branch.objects.first()
    context = {
        'appointment': appointment,
        'clinic_name': branch.name if branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': branch.logo.url if branch and branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': branch.footer_text if branch and branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'appointments/detail.html', context)

@login_required
def appointment_update(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)
    if request.method == 'POST':
        form = AppointmentForm(request.POST, instance=appointment)
        if form.is_valid():
            form.save()
            messages.success(request, f'تم تعديل الموعد بنجاح (رقم التذكرة: {appointment.id})')
            return redirect('appointment_list')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = AppointmentForm(instance=appointment)

    branch = Branch.objects.first()
    context = {
        'form': form,
        'clinic_name': branch.name if branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': branch.logo.url if branch and branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': branch.footer_text if branch and branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'appointments/update.html', context)

@login_required
def appointment_delete(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)
    if request.method == 'POST':
        appointment.delete()
        messages.success(request, 'تم حذف الموعد بنجاح')
        return redirect('appointment_list')
    branch = Branch.objects.first()
    context = {
        'appointment': appointment,
        'clinic_name': branch.name if branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': branch.logo.url if branch and branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': branch.footer_text if branch and branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'appointments/delete.html', context)

@login_required
def waiting_list(request):
    branch = Branch.objects.first()
    context = {
        'clinic_name': branch.name if branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': branch.logo.url if branch and branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': branch.footer_text if branch and branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'appointments/waiting_list.html', context)

@login_required
def waiting_list_data(request):
    appointments = Appointment.objects.filter(
        status__name='Scheduled',
        scheduled_date__date=timezone.now().date()
    ).order_by('scheduled_date')
    data = [{
        'id': appointment.id,
        'patient': appointment.patient.name,
        'doctor': appointment.doctor.name if appointment.doctor else 'غير محدد',
        'service': appointment.service.name if appointment.service else 'غير محدد',
        'scheduled_date': appointment.scheduled_date.strftime('%Y-%m-%d %H:%M:%S'),
        'status': appointment.status.name if appointment.status else 'غير محدد'
    } for appointment in appointments]
    return JsonResponse({'data': data})