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
import accounts.roles as _roles
from accounts.roles import (
    RECEPTION, is_clinic_admin, is_front_desk, is_owner,
    role_name, scope_queryset_to_user, sees_all_branches,
)

def is_reception_or_admin(user):
    return is_front_desk(user)

def can_view_patients(user):
    """Doctors need the patient file to reach the clinical record — but they
    do not register patients, which stays with Reception and Admin."""
    return _roles.can_view_patients(user)

@login_required
@user_passes_test(is_reception_or_admin)
def patient_create(request):
    if request.method == 'POST':
        form = PatientForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                check_limit(
                    request.user.tenant, 'max_patients',
                    Patient.objects.filter(needs_review=False).count(),
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
    patients = scope_queryset_to_user(patients, request.user)
    if role_name(request.user) == RECEPTION:
        patients = patients.values('uuid', 'serial_number', 'name', 'phone1', 'gender')
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
    patient = get_object_or_404(scope_queryset_to_user(Patient.objects.all(), request.user), uuid=uuid)
    # The group Owner sees every clinic; everyone else their own.
    if not sees_all_branches(request.user) and request.user.branch and patient.branch_id != request.user.branch_id:
        raise Http404
    appointments = Appointment.objects.filter(patient=patient).order_by('-scheduled_date', '-serial_number')
    if request.user.role.name == 'Reception':
        appointments = appointments.values('uuid', 'serial_number', 'doctor__name', 'service__name')
    payments = Payment.objects.filter(patient=patient).order_by('date') if is_clinic_admin(request.user) else []

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
@user_passes_test(is_clinic_admin)
def patient_update(request, uuid):
    patient = get_object_or_404(scope_queryset_to_user(Patient.objects.all(), request.user), uuid=uuid)
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
@user_passes_test(is_clinic_admin)
def patient_delete(request, uuid):
    patient = get_object_or_404(scope_queryset_to_user(Patient.objects.all(), request.user), uuid=uuid)
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
@user_passes_test(is_clinic_admin)
def patient_list_export(request):
    export_format = request.GET.get('export')
    patients = scope_queryset_to_user(Patient.objects.all(), request.user).order_by('-created_at', '-serial_number')
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

@login_required
@user_passes_test(is_front_desk)
def intake_form_print(request):
    """The printable intake form: the patient fills it in by hand and signs.

    Blank by default; `?patient=<uuid>` pre-fills what is already on record
    (the patient then checks and signs). The letterhead and which sections it
    asks for are the clinic's own (branches/printing.py) — `?branch=<uuid>`
    lets the Owner print another clinic's.
    """
    from branches.models import Branch
    from branches.printing import intake_layout, letterhead

    from accounts.roles import current_branch_id

    branch = None
    wanted = request.GET.get("branch")
    if wanted and sees_all_branches(request.user):
        branch = Branch.objects.filter(uuid=wanted).first()
    if branch is None:
        branch = Branch.objects.filter(pk=current_branch_id(request.user)).first()

    patient = None
    if request.GET.get("patient"):
        patient = get_object_or_404(
            scope_queryset_to_user(Patient.objects.all(), request.user), uuid=request.GET["patient"]
        )
        branch = patient.branch or branch

    return render(request, "print/intake_form.html", {
        "letterhead": letterhead(branch, request),
        "layout": intake_layout(branch),
        "patient": patient,
    })
