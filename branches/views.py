from django.shortcuts import render, redirect, get_object_or_404
from .forms import BranchForm
from .models import Branch
from django.conf import settings
from django.contrib import messages
from django.urls import reverse
from django.contrib.auth.decorators import login_required

@login_required
def branch_create(request):
    if request.method == 'POST':
        form = BranchForm(request.POST, request.FILES)
        if form.is_valid():
            branch = form.save()
            messages.success(request, f'تم إنشاء الفرع {branch.name} بنجاح')
            return redirect('branch_list')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = BranchForm()

    context = {
        'form': form,
        'clinic_name': getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'branches/create.html', context)

@login_required
def branch_list(request):
    branches = Branch.objects.all()
    context = {
        'branches': branches,
        'clinic_name': getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'branches/list.html', context)

@login_required
def branch_update(request, pk):
    branch = get_object_or_404(Branch, pk=pk)
    if request.method == 'POST':
        form = BranchForm(request.POST, request.FILES, instance=branch)
        if form.is_valid():
            form.save()
            messages.success(request, f'تم تعديل الفرع {branch.name} بنجاح')
            return redirect('branch_list')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = BranchForm(instance=branch)

    context = {
        'form': form,
        'clinic_name': getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'branches/update.html', context)

@login_required
def branch_delete(request, pk):
    branch = get_object_or_404(Branch, pk=pk)
    if request.method == 'POST':
        branch.delete()
        messages.success(request, 'تم حذف الفرع بنجاح')
        return redirect('branch_list')
    context = {
        'branch': branch,
        'clinic_name': getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'branches/delete.html', context)