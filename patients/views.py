from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import ProtectedError
from django.http import Http404
from .forms import PatientForm
from .models import Patient
from appointments.models import Appointment
from billing.models import Payment
from medical.models import (
    Allergy,
    LabResult,
    MedicalAttachment,
    TreatmentPlan,
    Visit,
)
from medical.permissions import can_view_clinical
from subscriptions.entitlements import LimitReached, check_limit
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from utils.utils import export_pdf, export_excel
from datetime import datetime

def is_reception_or_admin(user):
    return user.role.name in ['Reception', 'Admin'] if user.role else False

def can_view_patients(user):
    """Doctors need the patient file to reach the clinical record — but they
    do not register patients, which stays with Reception and Admin."""
    return user.role.name in ['Reception', 'Admin', 'Doctor'] if user.role else False

@login_required
@user_passes_test(is_reception_or_admin)
def patient_create(request):
    if request.method == 'POST':
        form = PatientForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                check_limit(
                    request.user.tenant, 'max_patients', Patient.objects.count()
                )
            except LimitReached as reached:
                messages.error(
                    request,
                    f'باقتك الحالية تسمح بـ {reached.allowed} مريض. '
                    'قم بترقية الباقة لتسجيل المزيد.',
                )
                return redirect('patients:patient_list')
            patient = form.save(commit=False)
            patient.tenant = request.user.tenant
            patient.save()
            messages.success(request, f'تم تسجيل المريض {patient.name} بنجاح')
            return redirect('patients:patient_list')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = PatientForm()
    context = {
        'form': form,
    }
    return render(request, 'patients/create.html', context)

@login_required
@user_passes_test(can_view_patients)
def patient_list(request):
    patients = Patient.objects.all().order_by('-created_at', '-serial_number')
    if request.user.role.name == 'Reception' and request.user.branch:
        patients = patients.filter(branch=request.user.branch).values('uuid', 'serial_number', 'name', 'phone1', 'gender')
    paginator = Paginator(patients, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'patients': page_obj,
        'page_obj': page_obj,
    }
    return render(request, 'patients/list.html', context)

@login_required
@user_passes_test(can_view_patients)
def patient_detail(request, uuid):
    patient = get_object_or_404(Patient, uuid=uuid)
    # Admin is org-wide by design; everyone else is held to their own branch.
    if request.user.role.name != 'Admin' and request.user.branch and patient.branch_id != request.user.branch_id:
        raise Http404
    appointments = Appointment.objects.filter(patient=patient).order_by('-scheduled_date', '-serial_number')
    if request.user.role.name == 'Reception':
        appointments = appointments.values('uuid', 'serial_number', 'doctor__name', 'service__name')
    payments = Payment.objects.filter(patient=patient).order_by('date') if request.user.role.name == 'Admin' else []

    # Reception books and bills but never sees a diagnosis — the queries are
    # skipped entirely rather than filtered in the template.
    show_clinical = can_view_clinical(request.user)

    context = {
        'patient': patient,
        'appointments': appointments,
        'payments': payments,
        'show_clinical': show_clinical,
        'visits': Visit.objects.filter(patient=patient) if show_clinical else [],
        'allergies': Allergy.objects.filter(patient=patient) if show_clinical else [],
        'treatment_plans': (
            TreatmentPlan.objects.filter(patient=patient) if show_clinical else []
        ),
        'lab_results': (
            LabResult.objects.filter(patient=patient) if show_clinical else []
        ),
        'attachments': (
            MedicalAttachment.objects.filter(patient=patient) if show_clinical else []
        ),
    }
    return render(request, 'patients/detail.html', context)

@login_required
@user_passes_test(lambda u: u.role.name == 'Admin' if u.role else False)
def patient_update(request, uuid):
    patient = get_object_or_404(Patient, uuid=uuid)
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
    }
    return render(request, 'patients/update.html', context)

@login_required
@user_passes_test(lambda u: u.role.name == 'Admin' if u.role else False)
def patient_delete(request, uuid):
    patient = get_object_or_404(Patient, uuid=uuid)
    if request.method == 'POST':
        try:
            patient.delete()
        except ProtectedError:
            # Medical records are PROTECT-ed: a patient with clinical history
            # must not be erasable, and failing loudly beats deleting quietly.
            messages.error(
                request,
                'لا يمكن حذف هذا المريض لوجود سجلات طبية مرتبطة به. '
                'السجلات الطبية يجب الاحتفاظ بها.',
            )
            return redirect('patients:patient_detail', uuid=patient.uuid)
        messages.success(request, 'تم حذف المريض بنجاح')
        return redirect('patients:patient_list')
    context = {
        'patient': patient,
    }
    return render(request, 'patients/delete.html', context)

@login_required
@user_passes_test(lambda u: u.role.name == 'Admin' if u.role else False)
def patient_list_export(request):
    export_format = request.GET.get('export')
    patients = Patient.objects.filter(branch=request.user.branch).order_by('-created_at', '-serial_number')
    data = [
        [p.serial_number, p.name, p.phone1 or 'غير محدد', p.get_gender_display() or 'غير محدد', p.birth_date.strftime('%Y-%m-%d') if p.birth_date else 'غير محدد', p.national_id or 'غير محدد']
        for p in patients
    ]
    headers = ['رقم المريض', 'الاسم', 'رقم الهاتف', 'الجنس', 'تاريخ الميلاد', 'الرقم القومي']
    title = f'قائمة المرضى - فرع {request.user.branch.name if request.user.branch else "الكل"}'
    filename = f'patients_list_{datetime.now().strftime("%Y%m%d")}'
    if export_format == 'pdf':
        return export_pdf(data, headers, title, filename)
    elif export_format == 'excel':
        return export_excel(data, headers, title, filename)
    return redirect('patients:patient_list')