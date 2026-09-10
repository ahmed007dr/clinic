from django.shortcuts import render, redirect, get_object_or_404
from .forms import EmployeeForm, EmployeeTypeForm, SpecializationForm
from .models import Employee, EmployeeType, Specialization
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from subscriptions.entitlements import LimitReached, check_limit
from subscriptions.usage import doctor_count, limit_message


def _is_doctor_type(employee_type):
    return getattr(employee_type, 'name', None) == 'Doctor'

def is_reception_or_admin(user):
    return user.role.name in ['Reception', 'Admin'] if user.role else False

@login_required
@user_passes_test(is_reception_or_admin)
def employee_create(request):
    if request.method == 'POST':
        form = EmployeeForm(request.POST)
        if form.is_valid():
            # Checked after is_valid (the employee type is only known once the
            # form has cleaned it) and before save — the same shape as
            # branch_create and patient_create (WIRE-003).
            try:
                check_limit(request.user.tenant, 'max_staff', Employee.objects.count())
                if _is_doctor_type(form.cleaned_data.get('employee_type')):
                    check_limit(request.user.tenant, 'max_doctors', doctor_count())
            except LimitReached as reached:
                messages.error(request, limit_message(reached))
                return redirect('employees:employee_list')
            employee = form.save(commit=False)
            employee.tenant = request.user.tenant
            employee.save()
            form.save_m2m()  # specializations — dropped silently without this
            messages.success(request, f'تم إنشاء الموظف {employee.name} بنجاح')
            return redirect('employees:employee_list')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = EmployeeForm()
    context = {
        'form': form,
    }
    return render(request, 'employees/create.html', context)

@login_required
@user_passes_test(is_reception_or_admin)
def employee_list(request):
    employees = Employee.objects.all().order_by('-hire_date', '-serial_number')
    if request.user.role.name == 'Reception' and request.user.branch:
        employees = employees.filter(branch=request.user.branch).values('uuid', 'serial_number', 'name', 'employee_type__name', 'branch__name', 'specializations__name')
    paginator = Paginator(employees, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'employees': page_obj,
        'page_obj': page_obj,
    }
    return render(request, 'employees/list.html', context)

@login_required
@user_passes_test(lambda u: u.role.name == 'Admin' if u.role else False)
def employee_update(request, uuid):
    employee = get_object_or_404(Employee, uuid=uuid)
    # Read before binding the form: ModelForm validation writes the submitted
    # values onto the instance, after which the old type is gone.
    was_doctor = _is_doctor_type(employee.employee_type)
    if request.method == 'POST':
        form = EmployeeForm(request.POST, instance=employee)
        if form.is_valid():
            # Moving someone *into* the Doctor type crosses the same limit by
            # a different door; a limit that only guards create has a bypass.
            if _is_doctor_type(form.cleaned_data.get('employee_type')) and not was_doctor:
                try:
                    check_limit(request.user.tenant, 'max_doctors', doctor_count())
                except LimitReached as reached:
                    messages.error(request, limit_message(reached))
                    return redirect('employees:employee_list')
            form.save()
            messages.success(request, f'تم تعديل الموظف {employee.name} بنجاح')
            return redirect('employees:employee_list')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = EmployeeForm(instance=employee)
    context = {
        'form': form,
    }
    return render(request, 'employees/update.html', context)

@login_required
@user_passes_test(lambda u: u.role.name == 'Admin' if u.role else False)
def employee_delete(request, uuid):
    employee = get_object_or_404(Employee, uuid=uuid)
    if request.method == 'POST':
        employee.delete()
        messages.success(request, 'تم حذف الموظف بنجاح')
        return redirect('employees:employee_list')
    context = {
        'employee': employee,
    }
    return render(request, 'employees/delete.html', context)

@login_required
@user_passes_test(lambda u: u.role.name == 'Admin' if u.role else False)
def employee_type_create(request):
    if request.method == 'POST':
        form = EmployeeTypeForm(request.POST)
        if form.is_valid():
            employee_type = form.save(commit=False)
            employee_type.tenant = request.user.tenant
            employee_type.save()
            messages.success(request, f'تم إنشاء نوع الموظف {employee_type.name} بنجاح')
            return redirect('employees:employee_type_list')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = EmployeeTypeForm()
    context = {
        'form': form,
    }
    return render(request, 'employees/employee_type_create.html', context)

@login_required
@user_passes_test(lambda u: u.role.name == 'Admin' if u.role else False)
def employee_type_list(request):
    employee_types = EmployeeType.objects.all().order_by('name')
    context = {
        'employee_types': employee_types,
    }
    return render(request, 'employees/employee_type_list.html', context)

@login_required
@user_passes_test(lambda u: u.role.name == 'Admin' if u.role else False)
def employee_type_update(request, uuid):
    employee_type = get_object_or_404(EmployeeType, uuid=uuid)
    if request.method == 'POST':
        form = EmployeeTypeForm(request.POST, instance=employee_type)
        if form.is_valid():
            form.save()
            messages.success(request, f'تم تعديل نوع الموظف {employee_type.name} بنجاح')
            return redirect('employees:employee_type_list')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = EmployeeTypeForm(instance=employee_type)
    context = {
        'form': form,
    }
    return render(request, 'employees/employee_type_update.html', context)

@login_required
@user_passes_test(lambda u: u.role.name == 'Admin' if u.role else False)
def employee_type_delete(request, uuid):
    employee_type = get_object_or_404(EmployeeType, uuid=uuid)
    if request.method == 'POST':
        employee_type.delete()
        messages.success(request, 'تم حذف نوع الموظف بنجاح')
        return redirect('employees:employee_type_list')
    context = {
        'employee_type': employee_type,
    }
    return render(request, 'employees/employee_type_delete.html', context)

@login_required
@user_passes_test(lambda u: u.role.name == 'Admin' if u.role else False)
def specialization_create(request):
    if request.method == 'POST':
        form = SpecializationForm(request.POST)
        if form.is_valid():
            specialization = form.save(commit=False)
            specialization.tenant = request.user.tenant
            specialization.save()
            messages.success(request, f'تم إنشاء التخصص {specialization.name} بنجاح')
            return redirect('employees:specialization_list')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = SpecializationForm()
    context = {
        'form': form,
    }
    return render(request, 'employees/specialization_create.html', context)

@login_required
@user_passes_test(lambda u: u.role.name == 'Admin' if u.role else False)
def specialization_list(request):
    specializations = Specialization.objects.all().order_by('name')
    context = {
        'specializations': specializations,
    }
    return render(request, 'employees/specialization_list.html', context)

@login_required
@user_passes_test(lambda u: u.role.name == 'Admin' if u.role else False)
def specialization_update(request, uuid):
    specialization = get_object_or_404(Specialization, uuid=uuid)
    if request.method == 'POST':
        form = SpecializationForm(request.POST, instance=specialization)
        if form.is_valid():
            form.save()
            messages.success(request, f'تم تعديل التخصص {specialization.name} بنجاح')
            return redirect('employees:specialization_list')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = SpecializationForm(instance=specialization)
    context = {
        'form': form,
    }
    return render(request, 'employees/specialization_update.html', context)

@login_required
@user_passes_test(lambda u: u.role.name == 'Admin' if u.role else False)
def specialization_delete(request, uuid):
    specialization = get_object_or_404(Specialization, uuid=uuid)
    if request.method == 'POST':
        specialization.delete()
        messages.success(request, 'تم حذف التخصص بنجاح')
        return redirect('employees:specialization_list')
    context = {
        'specialization': specialization,
    }
    return render(request, 'employees/specialization_delete.html', context)