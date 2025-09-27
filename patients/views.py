from django.shortcuts import render, redirect, get_object_or_404
from .forms import PatientForm
from .models import Patient
from appointments.models import Appointment
from billing.models import Payment
from django.conf import settings
from django.contrib import messages
from django.urls import reverse
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse

def is_reception_or_admin(user):
    return user.role.name in ['Reception', 'Admin'] if user.role else False

@login_required
@user_passes_test(is_reception_or_admin)
def patient_create(request):
    if request.method == 'POST':
        form = PatientForm(request.POST, request.FILES)
        if form.is_valid():
            patient = form.save()
            messages.success(request, f'تم تسجيل المريض {patient.name} بنجاح')
            return redirect('patients:patient_list')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = PatientForm()

    context = {
        'form': form,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'patients/create.html', context)

@login_required
@user_passes_test(is_reception_or_admin)
def patient_list(request):
    patients = Patient.objects.filter(branch=request.user.branch).order_by('name')

    context = {
        'patients': patients,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'patients/list.html', context)

@login_required
def patient_list_data(request):
    patients = Patient.objects.filter(branch=request.user.branch).order_by('name')
    data = [{
        'name': patient.name,
        'phone1': patient.phone1 or 'غير محدد',
        'gender': patient.get_gender_display() or 'غير محدد',
        'birth_date': patient.birth_date.strftime('%Y-%m-%d') if patient.birth_date else 'غير محدد',
        'national_id': patient.national_id or 'غير محدد',
        'actions': f'<a href="{reverse("patient_detail", args=[patient.pk])}" class="btn btn-sm btn-info">تفاصيل</a> <a href="{reverse("patient_update", args=[patient.pk])}" class="btn btn-sm btn-primary">تعديل</a> <a href="{reverse("patient_delete", args=[patient.pk])}" class="btn btn-sm btn-danger">حذف</a>' if request.user.role.name == 'Admin' else ''
    } for patient in patients]
    return JsonResponse({'data': data})

@login_required
@user_passes_test(lambda u: u.role.name == 'Admin' if u.role else False)
def patient_detail(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    appointments = Appointment.objects.filter(patient=patient).order_by('-scheduled_date')
    payments = Payment.objects.filter(patient=patient).order_by('-date')
    context = {
        'patient': patient,
        'appointments': appointments,
        'payments': payments,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'patients/detail.html', context)

@login_required
@user_passes_test(lambda u: u.role.name == 'Admin' if u.role else False)
def patient_update(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    if request.method == 'POST':
        form = PatientForm(request.POST, request.FILES, instance=patient)
        if form.is_valid():
            form.save()
            messages.success(request, f'تم تعديل المريض {patient.name} بنجاح')
            return redirect('patients:patient_list')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = PatientForm(instance=patient)

    context = {
        'form': form,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'patients/update.html', context)

@login_required
@user_passes_test(lambda u: u.role.name == 'Admin' if u.role else False)
def patient_delete(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    if request.method == 'POST':
        patient.delete()
        messages.success(request, 'تم حذف المريض بنجاح')
        return redirect('patients:patient_list')
    context = {
        'patient': patient,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'patients/delete.html', context)

@login_required
@user_passes_test(lambda u: u.role.name == 'Admin' if u.role else False)
def patient_list_export(request):
    export_format = request.GET.get('export')
    patients = Patient.objects.filter(branch=request.user.branch).order_by('name')
    data = [
        [p.name, p.phone1 or 'غير محدد', p.get_gender_display() or 'غير محدد', p.birth_date.strftime('%Y-%m-%d') if p.birth_date else 'غير محدد', p.national_id or 'غير محدد']
        for p in patients
    ]
    headers = ['الاسم', 'رقم الهاتف', 'الجنس', 'تاريخ الميلاد', 'الرقم القومي']
    title = f'قائمة المرضى - فرع {request.user.branch.name if request.user.branch else "الكل"}'
    filename = f'patients_list_{datetime.now().strftime("%Y%m%d")}'

    if export_format == 'pdf':
        return export_pdf(data, headers, title, filename)
    elif export_format == 'excel':
        return export_excel(data, headers, title, filename)
    return redirect('patients:patient_list')