from django.shortcuts import render, redirect, get_object_or_404
from .forms import PaymentForm, ExpenseForm, ExpenseCategoryForm
from .models import Payment, Expense, ExpenseCategory
from branches.models import Branch
from django.conf import settings
from django.contrib import messages
from django.urls import reverse
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Sum, Count
from datetime import datetime
from utils.utils import export_pdf, export_excel
from django.core.paginator import Paginator

def is_admin(user):
    return user.role.name == 'Admin' if user.role else False

@login_required
@user_passes_test(is_admin)
def payment_create(request):
    if request.method == 'POST':
        form = PaymentForm(request.POST)
        if form.is_valid():
            payment = form.save()
            messages.success(request, f'تم تسجيل الدفعة {payment.receipt_number} بنجاح')
            return redirect('billing:payment_list')  # تغيير التوجيه إلى قائمة الدفعات
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = PaymentForm()
    context = {
        'form': form,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'billing/create.html', context)

@login_required
def payment_list(request):
    payments = Payment.objects.all().order_by('-date') if is_admin(request.user) else Payment.objects.filter(branch=request.user.branch).order_by('-date')
    context = {
        'payments': payments,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'billing/list.html', context)

@login_required
@user_passes_test(is_admin)
def payment_update(request, pk):
    payment = get_object_or_404(Payment, pk=pk)
    if request.method == 'POST':
        form = PaymentForm(request.POST, instance=payment)
        if form.is_valid():
            form.save()
            messages.success(request, f'تم تعديل الدفعة {payment.receipt_number} بنجاح')
            return redirect('billing:payment_list')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = PaymentForm(instance=payment)
    context = {
        'form': form,
        'payment': payment,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'billing/payment_update.html', context)

@login_required
@user_passes_test(is_admin)
def payment_delete(request, pk):
    payment = get_object_or_404(Payment, pk=pk)
    if request.method == 'POST':
        payment.delete()
        messages.success(request, 'تم حذف الدفعة بنجاح')
        return redirect('billing:payment_list')
    context = {
        'payment': payment,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'billing/payment_delete.html', context)

@login_required
def payment_detail(request, pk):
    payment = get_object_or_404(Payment, pk=pk)
    context = {
        'payment': payment,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'billing/detail.html', context)

@login_required
@user_passes_test(is_admin)
def payment_list_export(request):
    payments = Payment.objects.all().order_by('-date') if is_admin(request.user) else Payment.objects.filter(branch=request.user.branch).order_by('-date')
    export_format = request.GET.get('export')
    data = [
        [p.receipt_number, p.patient.name, str(p.amount), p.method.name if p.method else 'غير محدد', p.date.strftime('%Y-%m-%d')]
        for p in payments
    ]
    headers = ['رقم الإيصال', 'المريض', 'المبلغ', 'طريقة الدفع', 'التاريخ']
    title = f'قائمة الدفعات - فرع {request.user.branch.name if request.user.branch else "الكل"}'
    filename = f'payment_list_{datetime.now().strftime("%Y%m%d")}'
    if export_format == 'pdf':
        return export_pdf(data, headers, title, filename)
    elif export_format == 'excel':
        return export_excel(data, headers, title, filename)
    return redirect('billing:payment_list')

@login_required
@user_passes_test(is_admin)
def expense_create(request):
    if request.method == 'POST':
        form = ExpenseForm(request.POST)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.created_by = request.user
            expense.save()
            messages.success(request, f'تم تسجيل المصروف بنجاح')
            return redirect('billing:expense_list')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = ExpenseForm()
    context = {
        'form': form,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'billing/expense_create.html', context)

@login_required
def expense_list(request):
    expenses = Expense.objects.all().order_by('-date') if is_admin(request.user) else Expense.objects.filter(branch=request.user.branch).order_by('-date')
    context = {
        'expenses': expenses,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'billing/expense_list.html', context)

@login_required
@user_passes_test(is_admin)
def expense_update(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    if request.method == 'POST':
        form = ExpenseForm(request.POST, instance=expense)
        if form.is_valid():
            form.save()
            messages.success(request, f'تم تعديل المصروف بنجاح')
            return redirect('billing:expense_list')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = ExpenseForm(instance=expense)
    context = {
        'form': form,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'billing/expense_update.html', context)

@login_required
@user_passes_test(is_admin)
def expense_delete(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    if request.method == 'POST':
        expense.delete()
        messages.success(request, 'تم حذف المصروف بنجاح')
        return redirect('billing:expense_list')
    context = {
        'expense': expense,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'billing/expense_delete.html', context)

@login_required
@user_passes_test(is_admin)
def expense_category_create(request):
    if request.method == 'POST':
        form = ExpenseCategoryForm(request.POST)
        if form.is_valid():
            category = form.save()
            messages.success(request, f'تم إنشاء فئة المصروف {category.name} بنجاح')
            return redirect('billing:expense_category_list')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = ExpenseCategoryForm()
    context = {
        'form': form,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'billing/expense_category_create.html', context)

@login_required
def expense_category_list(request):
    categories = ExpenseCategory.objects.all().order_by('name')
    context = {
        'categories': categories,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'billing/expense_category_list.html', context)

@login_required
@user_passes_test(is_admin)
def expense_category_update(request, pk):
    category = get_object_or_404(ExpenseCategory, pk=pk)
    if request.method == 'POST':
        form = ExpenseCategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, f'تم تعديل فئة المصروف {category.name} بنجاح')
            return redirect('billing:expense_category_list')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = ExpenseCategoryForm(instance=category)
    context = {
        'form': form,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'billing/expense_category_update.html', context)

@login_required
@user_passes_test(is_admin)
def expense_category_delete(request, pk):
    category = get_object_or_404(ExpenseCategory, pk=pk)
    if request.method == 'POST':
        category.delete()
        messages.success(request, 'تم حذف فئة المصروف بنجاح')
        return redirect('billing:expense_category_list')
    context = {
        'category': category,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'billing/expense_category_delete.html', context)

login_required
def financial_report(request):
    # معايير الفلترة العامة
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    branch_id = request.GET.get('branch_id')
    # معايير الفلترة لكل tab
    payments_search = request.GET.get('payments_search', '')
    expenses_search = request.GET.get('expenses_search', '')
    doctor_revenue_search = request.GET.get('doctor_revenue_search', '')
    non_employee_search = request.GET.get('non_employee_search', '')
    doctor_summary_search = request.GET.get('doctor_summary_search', '')
    branches_search = request.GET.get('branches_search', '')
    # أرقام الصفحات لكل tab
    page_payments = request.GET.get('page_payments', 1)
    page_expenses = request.GET.get('page_expenses', 1)
    page_doctor_revenue = request.GET.get('page_doctor_revenue', 1)
    page_non_employee = request.GET.get('page_non_employee', 1)
    page_doctor_summary = request.GET.get('page_doctor_summary', 1)
    page_branches = request.GET.get('page_branches', 1)

    # تصفية الدفعات والمصروفات
    payments = Payment.objects.all() if is_admin(request.user) else Payment.objects.filter(branch=request.user.branch)
    expenses = Expense.objects.all() if is_admin(request.user) else Expense.objects.filter(branch=request.user.branch)
    
    # تطبيق الفلترة العامة
    if start_date:
        payments = payments.filter(date__gte=start_date)
        expenses = expenses.filter(date__gte=start_date)
    if end_date:
        payments = payments.filter(date__lte=end_date)
        expenses = expenses.filter(date__lte=end_date)
    if branch_id:
        payments = payments.filter(branch_id=branch_id)
        expenses = expenses.filter(branch_id=branch_id)

    # فلترة الإيرادات (بحث حسب اسم المريض)
    if payments_search:
        payments = payments.filter(patient__name__icontains=payments_search)
    
    # فلترة المصروفات (بحث حسب اسم الموظف)
    if expenses_search:
        expenses = expenses.filter(employee__name__icontains=expenses_search)

    # إيرادات الأطباء (الدفعات المرتبطة بمواعيد لها طبيب)
    doctor_revenue = payments.filter(appointment__doctor__employee_type__name='Doctor')
    if doctor_revenue_search:
        doctor_revenue = doctor_revenue.filter(
            Q(patient__name__icontains=doctor_revenue_search) | 
            Q(appointment__doctor__name__icontains=doctor_revenue_search)
        )

    # إيرادات غير مرتبطة بالموظفين (الدفعات بدون طبيب)
    non_employee_revenue = payments.filter(appointment__doctor__isnull=True)
    if non_employee_search:
        non_employee_revenue = non_employee_revenue.filter(patient__name__icontains=non_employee_search)

    # إجمالي إيرادات وعدد الكشوفات لكل طبيب
    doctor_summary = payments.filter(appointment__doctor__employee_type__name='Doctor').values(
        'appointment__doctor__name'
    ).annotate(
        total_revenue=Sum('amount'),
        total_appointments=Count('appointment__id')
    ).order_by('appointment__doctor__name')
    if doctor_summary_search:
        doctor_summary = doctor_summary.filter(appointment__doctor__name__icontains=doctor_summary_search)

    # إيرادات ومصروفات الفروع
    branches_summary = Branch.objects.all().annotate(
        total_revenue=Sum('payment__amount'),
        total_expenses=Sum('expenses__amount')
    )
    if branches_search:
        branches_summary = branches_summary.filter(name__icontains=branches_search)

    # التقسيم إلى صفحات (20 سطرًا لكل صفحة)
    payments_paginator = Paginator(payments, 20)
    expenses_paginator = Paginator(expenses, 20)
    doctor_revenue_paginator = Paginator(doctor_revenue, 20)
    non_employee_paginator = Paginator(non_employee_revenue, 20)
    doctor_summary_paginator = Paginator(doctor_summary, 20)
    branches_paginator = Paginator(branches_summary, 20)

    payments_page = payments_paginator.get_page(page_payments)
    expenses_page = expenses_paginator.get_page(page_expenses)
    doctor_revenue_page = doctor_revenue_paginator.get_page(page_doctor_revenue)
    non_employee_page = non_employee_paginator.get_page(page_non_employee)
    doctor_summary_page = doctor_summary_paginator.get_page(page_doctor_summary)
    branches_page = branches_paginator.get_page(page_branches)

    total_revenue = payments.aggregate(Sum('amount'))['amount__sum'] or 0
    total_expenses = expenses.aggregate(Sum('amount'))['amount__sum'] or 0
    net_profit = total_revenue - total_expenses

    if request.GET.get('export'):
        data = [
            ['رقم الإيصال', 'المريض', 'الطبيب', 'المبلغ', 'التاريخ'],
            *[(p.receipt_number, p.patient.name, p.appointment.doctor.name if p.appointment.doctor else 'غير مرتبط', str(p.amount), p.date.strftime('%Y-%m-%d')) for p in payments],
            [],
            ['فئة المصروف', 'الموظف', 'المبلغ', 'التاريخ'],
            *[(e.category.name if e.category else 'غير محدد', e.employee.name if e.employee else 'غير محدد', str(e.amount), e.date.strftime('%Y-%m-%d')) for e in expenses],
            [],
            ['إجمالي الإيرادات', str(total_revenue)],
            ['إجمالي المصروفات', str(total_expenses)],
            ['صافي الربح', str(net_profit)],
        ]
        headers = ['المعاملة', 'الوصف', 'المبلغ', 'التاريخ']
        title = f'التقرير المالي لفرع {request.user.branch.name if request.user.branch else "الكل"}'
        filename = f'financial_report_{datetime.now().strftime("%Y%m%d")}'
        if request.GET.get('export') == 'pdf':
            return export_pdf(data, headers, title, filename)
        elif request.GET.get('export') == 'excel':
            return export_excel(data, headers, title, filename)

    branches = Branch.objects.all()
    context = {
        'payments': payments_page,
        'expenses': expenses_page,
        'doctor_revenue': doctor_revenue_page,
        'non_employee_revenue': non_employee_page,
        'doctor_summary': doctor_summary_page,
        'branches_summary': branches_page,
        'total_revenue': total_revenue,
        'total_expenses': total_expenses,
        'net_profit': net_profit,
        'branches': branches,
        'start_date': start_date,
        'end_date': end_date,
        'branch_id': branch_id,
        'payments_search': payments_search,
        'expenses_search': expenses_search,
        'doctor_revenue_search': doctor_revenue_search,
        'non_employee_search': non_employee_search,
        'doctor_summary_search': doctor_summary_search,
        'branches_search': branches_search,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'billing/financial_report.html', context)