from django.shortcuts import render, redirect, get_object_or_404
from .forms import AppointmentForm, SearchForm
from .models import Appointment
from branches.models import Branch
from employees.models import Employee
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.core.paginator import Paginator

# دالة للتحقق من دور موظف الاستقبال أو الأدمن
def is_reception_or_admin(user):
    return user.role.name in ['Reception', 'Admin'] if user.role else False

@login_required
@user_passes_test(is_reception_or_admin)
def appointment_create(request):
    if request.method == 'POST':
        form = AppointmentForm(request.POST)
        if form.is_valid():
            appointment = form.save(commit=False)
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
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'عيادة'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'جميع الحقوق محفوظة &copy; 2025')
    }
    return render(request, 'appointments/create.html', context)

@login_required
@user_passes_test(is_reception_or_admin)
def appointment_list(request):
    form = SearchForm(request.GET or None)
    appointments = Appointment.objects.all().order_by('-scheduled_date', '-serial_number')  # ترتيب حسب التاريخ والرقم التسلسلي
    if request.user.role.name == 'Reception' and request.user.branch:
        appointments = appointments.filter(branch=request.user.branch)
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
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'عيادة'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'جميع الحقوق محفوظة &copy; 2025')
    }
    return render(request, 'appointments/list.html', context)

@login_required
@user_passes_test(lambda u: u.role.name == 'Admin' if u.role else False)
def appointment_detail(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)
    context = {
        'appointment': appointment,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'عيادة'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'جميع الحقوق محفوظة &copy; 2025')
    }
    return render(request, 'appointments/detail.html', context)

@login_required
@user_passes_test(lambda u: u.role.name == 'Admin' if u.role else False)
def appointment_update(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)
    if request.method == 'POST':
        form = AppointmentForm(request.POST, instance=appointment)
        if form.is_valid():
            form.save()
            messages.success(request, f'تم تعديل الموعد بنجاح (رقم التذكرة: {appointment.id})')
            return redirect('appointments:appointment_list')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = AppointmentForm(instance=appointment)

    context = {
        'form': form,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'عيادة'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'جميع الحقوق محفوظة &copy; 2025')
    }
    return render(request, 'appointments/update.html', context)

@login_required
@user_passes_test(lambda u: u.role.name == 'Admin' if u.role else False)
def appointment_delete(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)
    if request.method == 'POST':
        appointment.delete()
        messages.success(request, 'تم حذف الموعد بنجاح')
        return redirect('appointments:appointment_list')
    context = {
        'appointment': appointment,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'عيادة'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'جميع الحقوق محفوظة &copy; 2025')
    }
    return render(request, 'appointments/delete.html', context)

@login_required
@user_passes_test(is_reception_or_admin)
def waiting_list(request):
    appointments = Appointment.objects.filter(
        status='waiting',
        scheduled_date__date=timezone.now().date()
    ).order_by('-scheduled_date', '-serial_number')
    if request.user.role.name == 'Reception' and request.user.branch:
        appointments = appointments.filter(branch=request.user.branch)
        appointments = appointments.select_related('patient', 'doctor', 'service')
    paginator = Paginator(appointments, 20) 
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'appointments': page_obj,
        'page_obj': page_obj,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'عيادة'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'جميع الحقوق محفوظة &copy; 2025')
    }
    return render(request, 'appointments/waiting_list.html', context)