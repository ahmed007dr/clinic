from django.db import models
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
    RECEPTION, can_view_patients, display_name, is_clinic_admin, is_front_desk, is_owner,
    role_name, scope_queryset_to_user, sees_all_branches,
)

# دالة للتحقق من دور موظف الاستقبال أو الأدمن
from billing.pricing import enforce as enforce_price


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
            # The contract price unless management sets one (billing.pricing).
            enforce_price(
                appointment, request.user, price_field="price",
                doctor=appointment.doctor, service=appointment.service,
            )
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


#: The queue ticket only makes sense before the patient has gone in — once
#: they are "entered" they are already with the doctor, and after that it is
#: history, not something to hand someone waiting.
TICKET_STATUSES = ("waiting", "called")
#: Who counts as "ahead" for the "متبقي" count: also "entered", since someone
#: already with the doctor is certainly ahead of someone still waiting.
QUEUE_STATUSES = ("waiting", "called", "entered")


@login_required
@user_passes_test(is_reception_or_admin)
def appointment_ticket_print(request, uuid):
    """The slip handed to a patient who is now waiting: check-in time, their
    doctor, how many are ahead of them for that doctor, who printed it and
    when (the group owner's rule, 2026-09-12) — so nobody forgets when they
    arrived or loses their place in the queue.

    Printable only for today's booking still waiting to be seen; the design —
    which of these lines show at all — is the clinic's own (branches.printing,
    api/views/print_settings.py).
    """
    from branches.printing import letterhead, ticket_layout

    appointment = get_object_or_404(
        scope_queryset_to_user(Appointment.objects.select_related("patient", "doctor", "branch"), request.user),
        uuid=uuid,
    )
    today = timezone.now().date()
    if appointment.status not in TICKET_STATUSES or appointment.scheduled_date.date() != today:
        return render(request, "print/_unavailable.html", {
            "message": "لا يمكن طباعة تذكرة الانتظار — الحجز ليس ضمن قائمة الانتظار اليوم.",
        })

    ahead_count = None
    if appointment.doctor_id is not None:
        ahead_count = Appointment.objects.filter(
            branch=appointment.branch, doctor_id=appointment.doctor_id,
            scheduled_date__date=today, status__in=QUEUE_STATUSES,
        ).filter(
            models.Q(scheduled_date__lt=appointment.scheduled_date)
            | models.Q(scheduled_date=appointment.scheduled_date, id__lt=appointment.id)
        ).count()

    return render(request, "appointments/ticket_print.html", {
        "letterhead": letterhead(appointment.branch, request),
        "layout": ticket_layout(appointment.branch),
        "appointment": appointment,
        "ahead_count": ahead_count,
        "checked_in_at": timezone.now(),
        "reception_name": display_name(request.user),
    })