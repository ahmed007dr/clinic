"""Server-rendered pages the React app still links to: the printable intake form
and the PDF / Excel export of the patient search. Everything else about
patients is the React app and the API."""

from datetime import datetime

from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render

from accounts.roles import is_clinic_admin, is_front_desk, scope_queryset_to_user, sees_all_branches
from utils.utils import export_excel, export_pdf

from .filters import narrow_patients, search_patients
from .models import Patient


@login_required
def patient_list_export(request):
    """PDF / Excel of the patients the search screen is showing: the same
    criteria (`patients.filters`), never the whole clinic unasked.

    A logged-in user who may not export gets a plain 403. `user_passes_test`
    would send them to the login page, which — already signed in — bounces
    them to the old dashboard, and the button just seemed to wander off.
    """
    if not is_clinic_admin(request.user):
        raise PermissionDenied('التصدير مقصور على إدارة العيادة.')
    export_format = request.GET.get('export')
    patients = scope_queryset_to_user(Patient.objects.filter(needs_review=False), request.user)
    patients = search_patients(narrow_patients(patients, request.GET), request.GET.get('search'))
    patients = patients.order_by('-created_at', '-serial_number')
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
    return HttpResponseBadRequest('صيغة التصدير غير معروفة: استخدم export=pdf أو export=excel.')


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
