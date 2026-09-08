from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from patients.models import Patient

from .forms import AllergyForm, VisitForm
from .models import Allergy, Visit
from .permissions import can_view_clinical, scoped_to_user

clinical_required = user_passes_test(can_view_clinical)


def _get_patient(request, patient_uuid):
    """Tenant scoping comes from the manager; this adds the branch layer."""
    patient = get_object_or_404(Patient, uuid=patient_uuid)
    role = request.user.role
    if role and role.name != "Admin" and request.user.branch_id:
        if patient.branch_id != request.user.branch_id:
            raise Http404
    return patient


def _get_visit(request, uuid):
    return get_object_or_404(scoped_to_user(Visit.objects.all(), request.user), uuid=uuid)


@login_required
@clinical_required
def visit_create(request, patient_uuid):
    patient = _get_patient(request, patient_uuid)

    if request.method == "POST":
        form = VisitForm(request.POST)
        if form.is_valid():
            visit = form.save(commit=False)
            visit.tenant = request.user.tenant
            visit.patient = patient
            visit.created_by = request.user
            if not visit.branch_id:
                visit.branch = patient.branch or request.user.branch
            visit.save()
            messages.success(request, f"تم تسجيل الزيارة {visit.serial_number} بنجاح")
            return redirect("medical:visit_detail", uuid=visit.uuid)
        messages.error(request, "خطأ في إدخال البيانات")
    else:
        form = VisitForm(initial={"branch": patient.branch or request.user.branch})

    return render(request, "medical/visit_form.html", {
        "form": form,
        "patient": patient,
        "is_new": True,
    })


@login_required
@clinical_required
def visit_detail(request, uuid):
    visit = _get_visit(request, uuid)
    return render(request, "medical/visit_detail.html", {
        "visit": visit,
        "patient": visit.patient,
        "allergies": Allergy.objects.filter(patient=visit.patient),
    })


@login_required
@clinical_required
def visit_update(request, uuid):
    visit = _get_visit(request, uuid)

    if request.method == "POST":
        form = VisitForm(request.POST, instance=visit)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تعديل الزيارة بنجاح")
            return redirect("medical:visit_detail", uuid=visit.uuid)
        messages.error(request, "خطأ في إدخال البيانات")
    else:
        form = VisitForm(instance=visit)

    return render(request, "medical/visit_form.html", {
        "form": form,
        "patient": visit.patient,
        "visit": visit,
        "is_new": False,
    })


@login_required
@clinical_required
def allergy_create(request, patient_uuid):
    patient = _get_patient(request, patient_uuid)

    if request.method == "POST":
        form = AllergyForm(request.POST)
        if form.is_valid():
            allergy = form.save(commit=False)
            allergy.tenant = request.user.tenant
            allergy.patient = patient
            allergy.recorded_by = request.user
            if Allergy.objects.filter(patient=patient, substance=allergy.substance).exists():
                messages.error(request, "هذه الحساسية مسجلة بالفعل لهذا المريض")
            else:
                allergy.save()
                messages.success(request, "تم تسجيل الحساسية بنجاح")
                return redirect("patients:patient_detail", uuid=patient.uuid)
        else:
            messages.error(request, "خطأ في إدخال البيانات")
    else:
        form = AllergyForm()

    return render(request, "medical/allergy_form.html", {"form": form, "patient": patient})
