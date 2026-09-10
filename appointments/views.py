from django.shortcuts import render, redirect, get_object_or_404
from .forms import AppointmentForm, SearchForm
from .models import Appointment
from branches.models import Branch
from employees.models import Employee
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.core.paginator import Paginator
from accounts.roles import (
    RECEPTION, can_view_patients, is_clinic_admin, is_front_desk, is_owner,
    role_name, scope_queryset_to_user, sees_all_branches,
)

# دالة للتحقق من دور موظف الاستقبال أو الأدمن
def is_reception_or_admin(user):
    return is_front_desk(user)

@login_required
@user_passes_test(is_reception_or_admin)
def appointment_create(request):
    if request.method == 'POST':
        form = AppointmentForm(request.POST)
        if form.is_valid():
            appointment = form.save(commit=False)
            appointment.tenant = request.user.tenant
            appointment.created_by = request.user
            appointment.save()  # serial_number يُولد تلقائيًا في save
            messages.success(request, f'تم حجز الموعد بنجاح (رقم التذكرة: {appointment.serial_number})')
            return redirect('appointments:appointment_list')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = AppointmentForm()

    context = {
        'form': form,
    }
    return render(request, 'appointments/create.html', context)

@login_required
@user_passes_test(is_reception_or_admin)
def appointment_list(request):
    form = SearchForm(request.GET or None)
    appointments = Appointment.objects.all().order_by('-scheduled_date', '-serial_number')  # ترتيب حسب التاريخ والرقم التسلسلي
    if not sees_all_branches(request.user):
        appointments = scope_queryset_to_user(appointments, request.user)
        if form.is_valid():
            query = form.cleaned_data.get('query')
            if query:
                appointments = appointments.filter(patient__name__icontains=query) | appointments.filter(doctor__name__icontains=query)
        appointments = appointments.select_related('patient', 'doctor', 'service')
    else:
        if form.is_valid():
            query = form.cleaned_data.get('query')
            if query:
                appointments = appointments.filter(patient__name__icontains=query) | appointments.filter(doctor__name__icontains=query)

    paginator = Paginator(appointments, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'appointments': page_obj,
        'form': form,
        'page_obj': page_obj,
    }
    return render(request, 'appointments/list.html', context)

@login_required
@user_passes_test(is_clinic_admin)
def appointment_detail(request, uuid):
    appointment = get_object_or_404(scope_queryset_to_user(Appointment.objects.all(), request.user), uuid=uuid)
    context = {
        'appointment': appointment,
    }
    return render(request, 'appointments/detail.html', context)

@login_required
@user_passes_test(is_clinic_admin)
def appointment_update(request, uuid):
    appointment = get_object_or_404(scope_queryset_to_user(Appointment.objects.all(), request.user), uuid=uuid)
    if request.method == 'POST':
        form = AppointmentForm(request.POST, instance=appointment)
        if form.is_valid():
            form.save()
            messages.success(request, f'تم تعديل الموعد بنجاح (رقم التذكرة: {appointment.serial_number})')
            return redirect('appointments:appointment_list')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = AppointmentForm(instance=appointment)

    context = {
        'form': form,
    }
    return render(request, 'appointments/update.html', context)

@login_required
@user_passes_test(is_clinic_admin)
def appointment_delete(request, uuid):
    appointment = get_object_or_404(scope_queryset_to_user(Appointment.objects.all(), request.user), uuid=uuid)
    if request.method == 'POST':
        appointment.delete()
        messages.success(request, 'تم حذف الموعد بنجاح')
        return redirect('appointments:appointment_list')
    context = {
        'appointment': appointment,
    }
    return render(request, 'appointments/delete.html', context)
@login_required
@user_passes_test(is_reception_or_admin)
def waiting_list(request):
    appointments = Appointment.objects.filter(
        status='waiting',
        scheduled_date__date=timezone.now().date()
    ).order_by('-scheduled_date', '-serial_number')
    if not sees_all_branches(request.user):
        appointments = scope_queryset_to_user(appointments, request.user)
        appointments = appointments.select_related('patient', 'doctor', 'service')
    paginator = Paginator(appointments, 20) 
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'appointments': page_obj,
        'page_obj': page_obj,
    }
    return render(request, 'appointments/waiting_list.html', context)