from django.shortcuts import render, redirect, get_object_or_404
from .forms import EmployeeForm, EmployeeTypeForm, SpecializationForm
from .models import Employee, EmployeeType, Specialization
from django.conf import settings
from django.contrib import messages
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from utils.utils import export_pdf, export_excel
from datetime import datetime

@login_required
def employee_create(request):
    if request.method == 'POST':
        form = EmployeeForm(request.POST)
        if form.is_valid():
            employee = form.save()
            messages.success(request, f'تم إنشاء الموظف {employee.name} بنجاح')
            return redirect('employee_list')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = EmployeeForm()

    context = {
        'form': form,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'employees/create.html', context)

@login_required
def employee_list(request):
    context = {
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'employees/list.html', context)

@login_required
def employee_list_data(request):
    employees = Employee.objects.filter(branch=request.user.branch)
    data = [{
        'name': employee.name,
        'employee_type': employee.employee_type.name if employee.employee_type else 'غير محدد',
        'phone1': employee.phone1 or 'غير محدد',
        'email': employee.email or 'غير محدد',
        'actions': f'<a href="{reverse("employee_update", args=[employee.pk])}" class="btn btn-sm btn-primary">تعديل</a> <a href="{reverse("employee_delete", args=[employee.pk])}" class="btn btn-sm btn-danger">حذف</a>'
    } for employee in employees]
    return JsonResponse({'data': data})

@login_required
def employee_update(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    if request.method == 'POST':
        form = EmployeeForm(request.POST, instance=employee)
        if form.is_valid():
            form.save()
            messages.success(request, f'تم تعديل الموظف {employee.name} بنجاح')
            return redirect('employee_list')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = EmployeeForm(instance=employee)

    context = {
        'form': form,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'employees/update.html', context)

@login_required
def employee_delete(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    if request.method == 'POST':
        employee.delete()
        messages.success(request, 'تم حذف الموظف بنجاح')
        return redirect('employee_list')
    context = {
        'employee': employee,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'employees/delete.html', context)

@login_required
def employee_type_create(request):
    if request.method == 'POST':
        form = EmployeeTypeForm(request.POST)
        if form.is_valid():
            employee_type = form.save()
            messages.success(request, f'تم إنشاء نوع الموظف {employee_type.name} بنجاح')
            return redirect('employee_type_list')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = EmployeeTypeForm()

    context = {
        'form': form,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'employees/employee_type_create.html', context)

@login_required
def employee_type_list(request):
    employee_types = EmployeeType.objects.all().order_by('name')
    context = {
        'employee_types': employee_types,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'employees/employee_type_list.html', context)

@login_required
def employee_type_update(request, pk):
    employee_type = get_object_or_404(EmployeeType, pk=pk)
    if request.method == 'POST':
        form = EmployeeTypeForm(request.POST, instance=employee_type)
        if form.is_valid():
            form.save()
            messages.success(request, f'تم تعديل نوع الموظف {employee_type.name} بنجاح')
            return redirect('employee_type_list')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = EmployeeTypeForm(instance=employee_type)

    context = {
        'form': form,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'employees/employee_type_update.html', context)

@login_required
def employee_type_delete(request, pk):
    employee_type = get_object_or_404(EmployeeType, pk=pk)
    if request.method == 'POST':
        employee_type.delete()
        messages.success(request, 'تم حذف نوع الموظف بنجاح')
        return redirect('employee_type_list')
    context = {
        'employee_type': employee_type,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'employees/employee_type_delete.html', context)

@login_required
def specialization_create(request):
    if request.method == 'POST':
        form = SpecializationForm(request.POST)
        if form.is_valid():
            specialization = form.save()
            messages.success(request, f'تم إنشاء التخصص {specialization.name} بنجاح')
            return redirect('specialization_list')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = SpecializationForm()

    context = {
        'form': form,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'employees/specialization_create.html', context)

@login_required
def specialization_list(request):
    specializations = Specialization.objects.all().order_by('name')
    context = {
        'specializations': specializations,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'employees/specialization_list.html', context)

@login_required
def specialization_update(request, pk):
    specialization = get_object_or_404(Specialization, pk=pk)
    if request.method == 'POST':
        form = SpecializationForm(request.POST, instance=specialization)
        if form.is_valid():
            form.save()
            messages.success(request, f'تم تعديل التخصص {specialization.name} بنجاح')
            return redirect('specialization_list')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = SpecializationForm(instance=specialization)

    context = {
        'form': form,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'employees/specialization_update.html', context)

@login_required
def specialization_delete(request, pk):
    specialization = get_object_or_404(Specialization, pk=pk)
    if request.method == 'POST':
        specialization.delete()
        messages.success(request, 'تم حذف التخصص بنجاح')