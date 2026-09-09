from django.shortcuts import render, redirect, get_object_or_404
from .forms import BranchForm
from .models import Branch
from subscriptions.entitlements import LimitReached, check_limit
from django.contrib import messages
from django.urls import reverse
from django.contrib.auth.decorators import login_required, user_passes_test

def is_admin(user):
    return user.role.name == 'Admin' if user.role else False

@login_required
@user_passes_test(is_admin)
def branch_create(request):
    if request.method == 'POST':
        form = BranchForm(request.POST, request.FILES)
        if form.is_valid():
            # Checked on the server, on the way in. Hiding the button would not
            # be a limit — the form posts perfectly well without it.
            try:
                check_limit(
                    request.user.tenant, 'max_branches', Branch.objects.count()
                )
            except LimitReached as reached:
                messages.error(
                    request,
                    f'باقتك الحالية تسمح بـ {reached.allowed} فرع. '
                    'قم بترقية الباقة لإضافة المزيد.',
                )
                return redirect('branches:branch_list')
            branch = form.save(commit=False)
            branch.tenant = request.user.tenant
            branch.save()
            messages.success(request, f'تم إنشاء الفرع {branch.name} بنجاح')
            return redirect('branches:branch_list')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = BranchForm()

    context = {
        'form': form,
    }
    return render(request, 'branches/create.html', context)

@login_required
def branch_list(request):
    branches = Branch.objects.all()
    context = {
        'branches': branches,
    }
    return render(request, 'branches/list.html', context)

@login_required
@user_passes_test(is_admin)
def branch_update(request, uuid):
    branch = get_object_or_404(Branch, uuid=uuid)
    if request.method == 'POST':
        form = BranchForm(request.POST, request.FILES, instance=branch)
        if form.is_valid():
            form.save()
            messages.success(request, f'تم تعديل الفرع {branch.name} بنجاح')
            return redirect('branches:branch_list')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = BranchForm(instance=branch)

    context = {
        'form': form,
    }
    return render(request, 'branches/update.html', context)

@login_required
@user_passes_test(is_admin)
def branch_delete(request, uuid):
    branch = get_object_or_404(Branch, uuid=uuid)
    if request.method == 'POST':
        branch.delete()
        messages.success(request, 'تم حذف الفرع بنجاح')
        return redirect('branches:branch_list')
    context = {
        'branch': branch,
    }
    return render(request, 'branches/delete.html', context)