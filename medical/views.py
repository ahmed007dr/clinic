from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from patients.models import Patient

from .forms import AllergyForm, PrescriptionForm, PrescriptionItemFormSet, VisitForm
from .models import Allergy, Prescription, Visit, allergy_conflicts
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


def _get_prescription(request, uuid):
    # A prescription has no branch of its own — it inherits the visit's.
    return get_object_or_404(
        scoped_to_user(Prescription.objects.all(), request.user, "visit__branch"),
        uuid=uuid,
    )


def _warn_about_allergies(request, prescription):
    """Non-blocking by design: doc/readme.md §26 lets the system surface a
    suggestion but never take the medical decision. The prescription is saved
    either way — the doctor is told, and decides."""
    conflicts = allergy_conflicts(
        prescription.patient, [item.medication for item in prescription.items.all()]
    )
    for medication, allergen in conflicts:
        messages.warning(
            request,
            f"تنبيه: المريض لديه حساسية مسجلة من «{allergen}» — "
            f"والدواء الموصوف «{medication}» قد يتعارض معها. المراجعة مطلوبة.",
        )
    return conflicts


@login_required
@clinical_required
def prescription_create(request, visit_uuid):
    visit = _get_visit(request, visit_uuid)

    if request.method == "POST":
        form = PrescriptionForm(request.POST)
        formset = PrescriptionItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            prescription = form.save(commit=False)
            prescription.tenant = request.user.tenant
            prescription.visit = visit
            prescription.patient = visit.patient
            prescription.created_by = request.user
            if not prescription.doctor_id:
                prescription.doctor = visit.doctor
            prescription.save()

            formset.instance = prescription
            for item in formset.save(commit=False):
                item.tenant = prescription.tenant
                item.save()
            for item in formset.deleted_objects:
                item.delete()

            _warn_about_allergies(request, prescription)
            messages.success(request, f"تم إصدار الروشتة {prescription.serial_number}")
            return redirect("medical:prescription_detail", uuid=prescription.uuid)
        messages.error(request, "خطأ في إدخال البيانات")
    else:
        form = PrescriptionForm(initial={"doctor": visit.doctor})
        formset = PrescriptionItemFormSet()

    return render(request, "medical/prescription_form.html", {
        "form": form,
        "formset": formset,
        "visit": visit,
        "patient": visit.patient,
        "allergies": Allergy.objects.filter(patient=visit.patient),
        "is_new": True,
    })


@login_required
@clinical_required
def prescription_detail(request, uuid):
    prescription = _get_prescription(request, uuid)
    return render(request, "medical/prescription_detail.html", {
        "prescription": prescription,
        "patient": prescription.patient,
        "allergies": Allergy.objects.filter(patient=prescription.patient),
    })


@login_required
@clinical_required
def prescription_update(request, uuid):
    prescription = _get_prescription(request, uuid)

    if request.method == "POST":
        form = PrescriptionForm(request.POST, instance=prescription)
        formset = PrescriptionItemFormSet(request.POST, instance=prescription)
        if form.is_valid() and formset.is_valid():
            form.save()
            for item in formset.save(commit=False):
                item.tenant = prescription.tenant
                item.save()
            for item in formset.deleted_objects:
                item.delete()
            _warn_about_allergies(request, prescription)
            messages.success(request, "تم تعديل الروشتة بنجاح")
            return redirect("medical:prescription_detail", uuid=prescription.uuid)
        messages.error(request, "خطأ في إدخال البيانات")
    else:
        form = PrescriptionForm(instance=prescription)
        formset = PrescriptionItemFormSet(instance=prescription)

    return render(request, "medical/prescription_form.html", {
        "form": form,
        "formset": formset,
        "visit": prescription.visit,
        "patient": prescription.patient,
        "prescription": prescription,
        "allergies": Allergy.objects.filter(patient=prescription.patient),
        "is_new": False,
    })


@login_required
@clinical_required
def prescription_print(request, uuid):
    """Print-friendly view. Rendered as HTML rather than generated as a PDF:
    the browser handles Arabic shaping and RTL correctly, which the reportlab
    exporter used elsewhere does not."""
    prescription = _get_prescription(request, uuid)
    return render(request, "medical/prescription_print.html", {
        "prescription": prescription,
        "patient": prescription.patient,
        "allergies": Allergy.objects.filter(patient=prescription.patient),
    })
