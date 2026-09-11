from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import Http404
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.encoding import iri_to_uri
from django.views.decorators.http import require_POST

from django.conf import settings

from patients.models import Patient

from .forms import (
    AllergyForm,
    LabResultForm,
    MedicalAttachmentForm,
    PrescriptionForm,
    PrescriptionItemFormSet,
    ProcedureForm,
    TreatmentPlanForm,
    TreatmentSessionForm,
    VisitForm,
)
from .models import (
    Allergy,
    LabResult,
    MedicalAttachment,
    Prescription,
    Procedure,
    TreatmentPlan,
    TreatmentSession,
    Visit,
    allergy_conflicts,
)
from .attachments import ALLOWED_EXTENSIONS
from subscriptions.entitlements import LimitReached
from subscriptions.usage import check_storage, limit_message

from .permissions import can_view_clinical, scoped_to_user
from accounts.roles import is_doctor, is_front_desk, sees_all_branches
from billing.pricing import enforce as enforce_price

clinical_required = user_passes_test(can_view_clinical)


def _sign_as_doctor(record, user):
    """A doctor's record carries their own name, whatever the form said —
    the same rule as the API (api/viewsets.py). Without it a doctor writing
    here could leave the doctor blank and lose sight of their own record, or
    write under a colleague's name."""
    if is_doctor(user) and user.employee_id:
        record.doctor_id = user.employee_id


def _price(record, user, previous=None):
    """Unit price and discount from the doctor's contract unless management
    sets them — the same rule as the API (billing.pricing)."""
    doctor = user.employee if is_doctor(user) and user.employee_id else record.doctor
    # A session delivers its plan's service when it names none of its own.
    service = record.service or getattr(getattr(record, "plan", None), "service", None)
    enforce_price(
        record, user, price_field="unit_price", discount_field="discount",
        doctor=doctor, service=service, previous=previous,
    )


def _get_patient(request, patient_uuid):
    """Tenant scoping comes from the manager; branch and doctor scoping from
    the same function every other screen uses. The hand-written branch check
    this replaces also let a user with no branch through to every patient."""
    return get_object_or_404(
        scoped_to_user(Patient.objects.all(), request.user), uuid=patient_uuid
    )


def _get_visit(request, uuid):
    return get_object_or_404(scoped_to_user(Visit.objects.all(), request.user), uuid=uuid)


@login_required
@clinical_required
def visit_create(request, patient_uuid):
    patient = _get_patient(request, patient_uuid)
    if is_doctor(request.user):
        # Same rule as the API: a visit is opened by the front desk sending the
        # patient in (medical/checkin.py), not by the doctor.
        messages.error(request, "تُسجَّل الزيارة من الاستقبال عند دخول المريض إليك.")
        return redirect("patients:patient_detail", uuid=patient.uuid)

    if request.method == "POST":
        form = VisitForm(request.POST)
        if form.is_valid():
            visit = form.save(commit=False)
            _sign_as_doctor(visit, request.user)
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
        "procedures": visit.procedures.all(),
    })


@login_required
@clinical_required
def visit_update(request, uuid):
    visit = _get_visit(request, uuid)

    if request.method == "POST":
        locked = (visit.doctor_id, visit.branch_id, visit.visit_date)
        form = VisitForm(request.POST, instance=visit)
        if form.is_valid():
            # Doctor, clinic and date are fixed once the visit exists — the
            # same rule as the API (VisitSerializer.LOCKED_ON_UPDATE).
            form.instance.doctor_id, form.instance.branch_id, form.instance.visit_date = locked
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


def _get_treatment_plan(request, uuid):
    return get_object_or_404(
        scoped_to_user(TreatmentPlan.objects.all(), request.user), uuid=uuid
    )


@login_required
@clinical_required
def treatment_plan_create(request, patient_uuid):
    patient = _get_patient(request, patient_uuid)

    if request.method == "POST":
        form = TreatmentPlanForm(request.POST)
        if form.is_valid():
            plan = form.save(commit=False)
            _sign_as_doctor(plan, request.user)
            plan.tenant = request.user.tenant
            plan.patient = patient
            plan.created_by = request.user
            if not plan.branch_id:
                plan.branch = patient.branch or request.user.branch
            plan.save()
            messages.success(request, f"تم إنشاء خطة العلاج {plan.serial_number} بنجاح")
            return redirect("medical:treatment_plan_detail", uuid=plan.uuid)
        messages.error(request, "خطأ في إدخال البيانات")
    else:
        form = TreatmentPlanForm(initial={"branch": patient.branch or request.user.branch})

    return render(request, "medical/treatment_plan_form.html", {
        "form": form,
        "patient": patient,
        "is_new": True,
    })


@login_required
@clinical_required
def treatment_plan_detail(request, uuid):
    plan = _get_treatment_plan(request, uuid)
    return render(request, "medical/treatment_plan_detail.html", {
        "plan": plan,
        "patient": plan.patient,
        "sessions": plan.sessions.all(),
    })


@login_required
@clinical_required
def treatment_plan_update(request, uuid):
    plan = _get_treatment_plan(request, uuid)

    if request.method == "POST":
        form = TreatmentPlanForm(request.POST, instance=plan)
        if form.is_valid():
            _sign_as_doctor(form.instance, request.user)
            form.save()
            messages.success(request, "تم تعديل خطة العلاج بنجاح")
            return redirect("medical:treatment_plan_detail", uuid=plan.uuid)
        messages.error(request, "خطأ في إدخال البيانات")
    else:
        form = TreatmentPlanForm(instance=plan)

    return render(request, "medical/treatment_plan_form.html", {
        "form": form,
        "patient": plan.patient,
        "plan": plan,
        "is_new": False,
    })


def _get_session(request, uuid):
    # A session has no branch requirement of its own to fall back on — it is
    # reached through its plan, so scope on the plan's branch.
    return get_object_or_404(
        scoped_to_user(TreatmentSession.objects.all(), request.user, "plan__branch"),
        uuid=uuid,
    )


@login_required
@clinical_required
def session_create(request, plan_uuid):
    plan = _get_treatment_plan(request, plan_uuid)

    if request.method == "POST":
        form = TreatmentSessionForm(request.POST)
        if form.is_valid():
            session = form.save(commit=False)
            _sign_as_doctor(session, request.user)
            session.tenant = request.user.tenant
            session.plan = plan
            session.patient = plan.patient
            session.created_by = request.user
            if not session.branch_id:
                session.branch = plan.branch or request.user.branch
            _price(session, request.user)
            session.save()
            messages.success(request, f"تم تسجيل الجلسة رقم {session.sequence}")
            return redirect("medical:treatment_plan_detail", uuid=plan.uuid)
        messages.error(request, "خطأ في إدخال البيانات")
    else:
        # Seeded from the plan so the common case is one click. §29's pricing
        # engine will replace how this number is worked out, not where it goes.
        form = TreatmentSessionForm(initial={
            "service": plan.service,
            "doctor": plan.doctor,
            "branch": plan.branch or request.user.branch,
            "unit_price": plan.service.base_price if plan.service else 0,
        })

    return render(request, "medical/treatment_session_form.html", {
        "form": form,
        "plan": plan,
        "patient": plan.patient,
        "is_new": True,
    })


@login_required
@clinical_required
def session_detail(request, uuid):
    session = _get_session(request, uuid)
    return render(request, "medical/treatment_session_detail.html", {
        "session": session,
        "plan": session.plan,
        "patient": session.patient,
    })


@login_required
@clinical_required
def session_update(request, uuid):
    session = _get_session(request, uuid)

    if request.method == "POST":
        previous = TreatmentSession.all_objects.get(pk=session.pk)
        form = TreatmentSessionForm(request.POST, instance=session)
        if form.is_valid():
            _price(form.instance, request.user, previous)
            _sign_as_doctor(form.instance, request.user)
            form.save()
            messages.success(request, "تم تعديل الجلسة بنجاح")
            return redirect("medical:session_detail", uuid=session.uuid)
        messages.error(request, "خطأ في إدخال البيانات")
    else:
        form = TreatmentSessionForm(instance=session)

    return render(request, "medical/treatment_session_form.html", {
        "form": form,
        "plan": session.plan,
        "patient": session.patient,
        "session": session,
        "is_new": False,
    })





def _get_attachment(request, uuid):
    return get_object_or_404(
        scoped_to_user(MedicalAttachment.objects.all(), request.user), uuid=uuid
    )


@login_required
@clinical_required
def attachment_upload(request, patient_uuid):
    patient = _get_patient(request, patient_uuid)

    if request.method == "POST":
        form = MedicalAttachmentForm(request.POST, request.FILES)
        if form.is_valid():
            # Before anything is written: the size is known from the upload,
            # and refusing afterwards would leave the file on disk (WIRE-004).
            try:
                check_storage(request.user.tenant, form.cleaned_data["file"].size)
            except LimitReached as reached:
                messages.error(request, limit_message(reached))
                return redirect("patients:patient_detail", uuid=patient.uuid)
            attachment = form.save(commit=False)
            attachment.tenant = request.user.tenant
            attachment.patient = patient
            attachment.uploaded_by = request.user
            if not attachment.branch_id:
                attachment.branch = patient.branch or request.user.branch
            attachment.save()
            messages.success(request, f"تم رفع المستند {attachment.serial_number}")
            return redirect("patients:patient_detail", uuid=patient.uuid)
        messages.error(request, "خطأ في رفع الملف")
    else:
        form = MedicalAttachmentForm(
            initial={"branch": patient.branch or request.user.branch}
        )

    return render(request, "medical/attachment_form.html", {
        "form": form,
        "patient": patient,
        "max_megabytes": settings.MEDICAL_ATTACHMENT_MAX_BYTES // (1024 * 1024),
        "allowed": ", ".join(sorted(e.lstrip(".") for e in ALLOWED_EXTENSIONS)),
    })


@login_required
@clinical_required
def attachment_download(request, uuid):
    """The only way a stored attachment reaches a browser.

    Everything that protects these files is here rather than in the filesystem:
    the login check, the clinical role check, and `scoped_to_user`, which
    applies the tenant boundary and the branch boundary. A file served straight
    off disk by a web server would have none of them, which is why these are
    stored outside MEDIA_ROOT in the first place.

    Served as an attachment with the content type detected at upload, never the
    one the browser claimed. Serving a user-supplied type inline is how an
    uploaded file becomes stored XSS.
    """
    attachment = _get_attachment(request, uuid)

    filename = attachment.original_filename or f"{attachment.serial_number}"
    response = FileResponse(
        attachment.file.open("rb"),
        content_type=attachment.content_type or "application/octet-stream",
    )
    # filename* carries the Arabic names these documents actually have; the
    # plain filename is the ASCII fallback for older clients.
    response["Content-Disposition"] = (
        f"attachment; filename=\"{attachment.serial_number}\"; "
        f"filename*=UTF-8''{iri_to_uri(filename)}"
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response


def _get_lab_result(request, uuid):
    # Scoped on the result's own branch: a result can arrive with no visit
    # attached, so there is nothing else to inherit from.
    return get_object_or_404(
        scoped_to_user(LabResult.objects.all(), request.user), uuid=uuid
    )


@login_required
@clinical_required
def lab_result_create(request, patient_uuid):
    patient = _get_patient(request, patient_uuid)

    if request.method == "POST":
        form = LabResultForm(request.POST)
        if form.is_valid():
            result = form.save(commit=False)
            result.tenant = request.user.tenant
            result.patient = patient
            result.created_by = request.user
            if not result.branch_id:
                result.branch = patient.branch or request.user.branch
            result.save()
            messages.success(request, f"تم تسجيل التحليل {result.serial_number}")
            return redirect("medical:lab_result_detail", uuid=result.uuid)
        messages.error(request, "خطأ في إدخال البيانات")
    else:
        form = LabResultForm(initial={"branch": patient.branch or request.user.branch})

    return render(request, "medical/lab_result_form.html", {
        "form": form,
        "patient": patient,
        "is_new": True,
    })


@login_required
@clinical_required
def lab_result_detail(request, uuid):
    result = _get_lab_result(request, uuid)
    return render(request, "medical/lab_result_detail.html", {
        "result": result,
        "patient": result.patient,
    })


@login_required
@clinical_required
def lab_result_update(request, uuid):
    result = _get_lab_result(request, uuid)

    if request.method == "POST":
        form = LabResultForm(request.POST, instance=result)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تعديل التحليل بنجاح")
            return redirect("medical:lab_result_detail", uuid=result.uuid)
        messages.error(request, "خطأ في إدخال البيانات")
    else:
        form = LabResultForm(instance=result)

    return render(request, "medical/lab_result_form.html", {
        "form": form,
        "patient": result.patient,
        "result": result,
        "is_new": False,
    })


@login_required
@clinical_required
@require_POST
def lab_result_acknowledge(request, uuid):
    """Records that a clinician has read the result.

    Its own endpoint, and POST-only, for two reasons: signing off an abnormal
    result is a clinical act rather than an edit, and a GET would let a crawler
    or a prefetch acknowledge it by accident.
    """
    result = _get_lab_result(request, uuid)
    if result.acknowledge(request.user):
        messages.success(request, f"تم تسجيل اطلاعك على التحليل {result.serial_number}")
    else:
        messages.info(request, "هذا التحليل مسجل الاطلاع عليه بالفعل")
    return redirect("medical:lab_result_detail", uuid=result.uuid)


def _get_procedure(request, uuid):
    # A procedure has no branch of its own to fall back on — it is reached
    # through its visit, so scope on the visit's branch, as prescriptions do.
    return get_object_or_404(
        scoped_to_user(Procedure.objects.all(), request.user, "visit__branch"),
        uuid=uuid,
    )


@login_required
@clinical_required
def procedure_create(request, visit_uuid):
    visit = _get_visit(request, visit_uuid)

    if request.method == "POST":
        form = ProcedureForm(request.POST)
        if form.is_valid():
            procedure = form.save(commit=False)
            _sign_as_doctor(procedure, request.user)
            procedure.tenant = request.user.tenant
            procedure.visit = visit
            procedure.patient = visit.patient
            procedure.created_by = request.user
            if not procedure.doctor_id:
                procedure.doctor = visit.doctor
            if not procedure.branch_id:
                procedure.branch = visit.branch or request.user.branch
            _price(procedure, request.user)
            procedure.save()
            messages.success(request, f"تم تسجيل الإجراء {procedure.serial_number}")
            return redirect("medical:procedure_detail", uuid=procedure.uuid)
        messages.error(request, "خطأ في إدخال البيانات")
    else:
        form = ProcedureForm(initial={
            "doctor": visit.doctor,
            "branch": visit.branch or request.user.branch,
            "performed_at": visit.visit_date,
        })

    return render(request, "medical/procedure_form.html", {
        "form": form,
        "visit": visit,
        "patient": visit.patient,
        "is_new": True,
    })


@login_required
@clinical_required
def procedure_detail(request, uuid):
    procedure = _get_procedure(request, uuid)
    return render(request, "medical/procedure_detail.html", {
        "procedure": procedure,
        "visit": procedure.visit,
        "patient": procedure.patient,
    })


@login_required
@clinical_required
def procedure_update(request, uuid):
    procedure = _get_procedure(request, uuid)

    if request.method == "POST":
        previous = Procedure.all_objects.get(pk=procedure.pk)
        form = ProcedureForm(request.POST, instance=procedure)
        if form.is_valid():
            _price(form.instance, request.user, previous)
            _sign_as_doctor(form.instance, request.user)
            form.save()
            messages.success(request, "تم تعديل الإجراء بنجاح")
            return redirect("medical:procedure_detail", uuid=procedure.uuid)
        messages.error(request, "خطأ في إدخال البيانات")
    else:
        form = ProcedureForm(instance=procedure)

    return render(request, "medical/procedure_form.html", {
        "form": form,
        "visit": procedure.visit,
        "patient": procedure.patient,
        "procedure": procedure,
        "is_new": False,
    })


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
            _sign_as_doctor(prescription, request.user)
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
            _sign_as_doctor(form.instance, request.user)
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
@user_passes_test(lambda user: can_view_clinical(user) or is_front_desk(user))
def prescription_print(request, uuid):
    """Print-friendly view. Rendered as HTML rather than generated as a PDF:
    the browser handles Arabic shaping and RTL correctly, which the reportlab
    exporter used elsewhere does not.

    Open to the front desk as well (the group owner's rule, 2026-09-11):
    reception prints the sheet for the doctor to sign. It is the one clinical
    page they reach — the printed prescription, which the patient is handed
    anyway — and only within their own clinic."""
    from branches.printing import doctor_signature, letterhead

    prescription = _get_prescription(request, uuid)
    return render(request, "medical/prescription_print.html", {
        # The clinic's own letterhead — the same one as its intake form.
        "letterhead": letterhead(prescription.visit.branch, request),
        "doctor_signature": doctor_signature(prescription.doctor) if prescription.doctor else None,
        "prescription": prescription,
        "patient": prescription.patient,
        "allergies": Allergy.objects.filter(patient=prescription.patient),
    })
