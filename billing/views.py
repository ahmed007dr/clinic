from django.shortcuts import render, redirect, get_object_or_404
from .forms import PaymentForm, ExpenseForm, ExpenseCategoryForm
from .models import Payment, Expense, ExpenseCategory
from branches.models import Branch
from django.conf import settings
from django.contrib import messages
from django.urls import reverse
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Sum
from datetime import datetime
from utils.utils import export_pdf, export_excel
from django.http import JsonResponse

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
            return redirect('appointments:appointment_list')
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
    context = {
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'billing/list.html', context)

@login_required
def payment_list_data(request):
    #payments = Payment.objects.filter(branch=request.user.branch).order_by('-date')
    payments = Payment.objects.all() 

    print(request.user.branch)
    print(Payment.objects.filter(branch=request.user.branch).count())
    data = [{
        'receipt_number': payment.receipt_number,
        'patient': payment.patient.name,
        'amount': str(payment.amount),
        'method': payment.method.name if payment.method else 'غير محدد',
        'date': payment.date.strftime('%Y-%m-%d'),
        'actions': f'<a href="{reverse("payment_detail", args=[payment.pk])}" class="btn btn-sm btn-info">تفاصيل</a> <a href="{reverse("payment_update", args=[payment.pk])}" class="btn btn-sm btn-primary">تعديل</a> <a href="{reverse("payment_delete", args=[payment.pk])}" class="btn btn-sm btn-danger">حذف</a>' if is_admin(request.user) else f'<a href="{reverse("payment_detail", args=[payment.pk])}" class="btn btn-sm btn-info">تفاصيل</a>'
    } for payment in payments]
    return JsonResponse({'data': data})

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
def payment_list_export(request):
    export_format = request.GET.get('export')
    payments = Payment.objects.filter(branch=request.user.branch).order_by('-date')
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
   # expenses = Expense.objects.filter(branch=request.user.branch).order_by('-date')
    expenses = Expense.objects.all().order_by('-date') 
    context = {
        'expenses': expenses,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'billing/expense_list.html', context)

    
@login_required
def expense_list_data(request):
    expenses = Expense.objects.filter(branch=request.user.branch).order_by('-date')
    data = [{
        'branch': expense.branch.name if expense.branch else 'غير محدد',
        'category': expense.category.name if expense.category else 'غير محدد',
        'employee': expense.employee.name if expense.employee else 'غير محدد',
        'amount': str(expense.amount),
        'date': expense.date.strftime('%Y-%m-%d'),
        'actions': f'<a href="{reverse("expense_update", args=[expense.pk])}" class="btn btn-sm btn-primary">تعديل</a> <a href="{reverse("expense_delete", args=[expense.pk])}" class="btn btn-sm btn-danger">حذف</a>'
    } for expense in expenses]
    return JsonResponse({'data': data})

@login_required
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

@login_required
def financial_report(request):
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    branch_id = request.GET.get('branch_id')
    export_format = request.GET.get('export')

    payments = Payment.objects.filter(branch=request.user.branch)
    expenses = Expense.objects.filter(branch=request.user.branch)
    # payments = Payment.objects.all()
    # expenses = Expense.objects.all()

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