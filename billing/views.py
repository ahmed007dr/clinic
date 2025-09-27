from django.shortcuts import render, redirect, get_object_or_404
from .forms import PaymentForm, ExpenseForm, ExpenseCategoryForm
from .models import Payment, Expense, ExpenseCategory
from branches.models import Branch
from django.conf import settings
from django.contrib import messages
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from datetime import datetime
from utils import export_pdf, export_excel

@login_required
def payment_create(request):
    if request.method == 'POST':
        form = PaymentForm(request.POST)
        if form.is_valid():
            payment = form.save()
            messages.success(request, f'تم تسجيل الدفعة {payment.receipt_number} بنجاح')
            return redirect('appointment_list')
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
    payments = Payment.objects.filter(branch=request.user.branch).order_by('-date')
    context = {
        'payments': payments,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'billing/list.html', context)

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
def expense_create(request):
    if request.method == 'POST':
        form = ExpenseForm(request.POST)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.created_by = request.user
            expense.save()
            messages.success(request, f'تم تسجيل المصروف بنجاح')
            return redirect('expense_list')
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
    expenses = Expense.objects.filter(branch=request.user.branch).order_by('-date')
    context = {
        'expenses': expenses,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'billing/expense_list.html', context)

@login_required
def expense_update(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    if request.method == 'POST':
        form = ExpenseForm(request.POST, instance=expense)
        if form.is_valid():
            form.save()
            messages.success(request, f'تم تعديل المصروف بنجاح')
            return redirect('expense_list')
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
def expense_delete(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    if request.method == 'POST':
        expense.delete()
        messages.success(request, 'تم حذف المصروف بنجاح')
        return redirect('expense_list')
    context = {
        'expense': expense,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'billing/expense_delete.html', context)

@login_required
def expense_category_create(request):
    if request.method == 'POST':
        form = ExpenseCategoryForm(request.POST)
        if form.is_valid():
            category = form.save()
            messages.success(request, f'تم إنشاء فئة المصروف {category.name} بنجاح')
            return redirect('expense_category_list')
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
def expense_category_update(request, pk):
    category = get_object_or_404(ExpenseCategory, pk=pk)
    if request.method == 'POST':
        form = ExpenseCategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, f'تم تعديل فئة المصروف {category.name} بنجاح')
            return redirect('expense_category_list')
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
def expense_category_delete(request, pk):
    category = get_object_or_404(ExpenseCategory, pk=pk)
    if request.method == 'POST':
        category.delete()
        messages.success(request, 'تم حذف فئة المصروف بنجاح')
        return redirect('expense_category_list')
    context = {
        'category': category,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'billing/expense_category_delete.html', context)

@login_required
def financial_report(request):
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    branch_id = request.GET.get('branch_id')
    export_format = request.GET.get('export')

    payments = Payment.objects.filter(branch=request.user.branch)
    expenses = Expense.objects.filter(branch=request.user.branch)

    if start_date:
        payments = payments.filter(date__gte=start_date)
        expenses = expenses.filter(date__gte=start_date)
    if end_date:
        payments = payments.filter(date__lte=end_date)
        expenses = expenses.filter(date__lte=end_date)
    if branch_id:
        payments = payments.filter(branch_id=branch_id)
        expenses = expenses.filter(branch_id=branch_id)

    total_revenue = payments.aggregate(Sum('amount'))['amount__sum'] or 0
    total_expenses = expenses.aggregate(Sum('amount'))['amount__sum'] or 0
    net_profit = total_revenue - total_expenses

    # تصدير البيانات
    if export_format:
        data = [
            ['رقم الإيصال', 'المريض', 'المبلغ', 'التاريخ'],
            *[(p.receipt_number, p.patient.name, str(p.amount), p.date.strftime('%Y-%m-%d')) for p in payments],
            [],
            ['فئة المصروف', 'الموظف', 'المبلغ', 'التاريخ'],
            *[(e.category.name, e.employee.name if e.employee else 'غير محدد', str(e.amount), e.date.strftime('%Y-%m-%d')) for e in expenses],
            [],
            ['إجمالي الإيرادات', str(total_revenue)],
            ['إجمالي المصروفات', str(total_expenses)],
            ['صافي الربح', str(net_profit)],
        ]
        headers = ['المعاملة', 'الوصف', 'المبلغ', 'التاريخ']
        title = f'التقرير المالي لفرع {request.user.branch.name if request.user.branch else "الكل"}'
        filename = f'financial_report_{datetime.now().strftime("%Y%m%d")}'

        if export_format == 'pdf':
            return export_pdf(data, headers, title, filename)
        elif export_format == 'excel':
            return export_excel(data, headers, title, filename)

    branches = Branch.objects.all()
    context = {
        'total_revenue': total_revenue,
        'total_expenses': total_expenses,
        'net_profit': net_profit,
        'branches': branches,
        'start_date': start_date,
        'end_date': end_date,
        'branch_id': branch_id,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'billing/financial_report.html', context)