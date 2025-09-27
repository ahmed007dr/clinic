from django.core.mail import EmailMessage
from django.utils import timezone
from django.db.models import Sum, Count
from django.template.loader import render_to_string
from datetime import datetime, timedelta
from billing.models import Payment, Expense, PaymentMethod
from branches.models import Branch
from employees.models import Employee
from services.models import Service
from django.conf import settings
from .models import ReportRecipient

def generate_daily_report():
    today = timezone.now().date()
    branches = Branch.objects.all()
    recipients = ReportRecipient.objects.filter(is_active=True).values_list('email', flat=True)
    for branch in branches:
        # بيانات اليوم
        branch_payments = Payment.objects.filter(branch=branch, date__date=today)
        day_total_incomes = branch_payments.aggregate(Sum('amount'))['amount__sum'] or 0
        branch_expenses = Expense.objects.filter(branch=branch, date=today)
        day_total_expenses = branch_expenses.aggregate(Sum('amount'))['amount__sum'] or 0
        day_net_profit = day_total_incomes - day_total_expenses

        # بيانات الشهر
        start_date = today.replace(day=1)
        month_payments = Payment.objects.filter(branch=branch, date__date__range=(start_date, today))
        month_total_incomes = month_payments.aggregate(Sum('amount'))['amount__sum'] or 0
        month_expenses = Expense.objects.filter(branch=branch, date__range=(start_date, today))
        month_total_expenses = month_expenses.aggregate(Sum('amount'))['amount__sum'] or 0
        month_net_profit = month_total_incomes - month_total_expenses

        # طرق الدفع
        payment_methods = PaymentMethod.objects.filter(
            payment__branch=branch, payment__date__date=today
        ).annotate(
            total_amount=Sum('payment__amount'), count=Count('payment')
        )

        # إيرادات الأطباء
        doctors = Employee.objects.filter(employee_type__name='Doctor', branch=branch)
        doctor_details = []
        for doctor in doctors:
            doctor_revenue = Payment.objects.filter(
                appointment__doctor=doctor, date__date=today
            ).aggregate(total_revenue=Sum('amount'), count=Count('id'))
            doctor_details.append({
                'name': doctor.name,
                'total_revenue': doctor_revenue['total_revenue'] or 0,
                'count': doctor_revenue['count']
            })

        # الإيرادات غير المرتبطة بطبيب
        no_doctor_revenue = Payment.objects.filter(
            appointment__doctor__isnull=True, branch=branch, date__date=today
        ).aggregate(Sum('amount'))['amount__sum'] or 0

        context = {
            'clinic_name': branch.name,
            'date': today.strftime('%Y-%m-%d'),
            'day_total_incomes': day_total_incomes,
            'day_total_expenses': day_total_expenses,
            'day_net_profit': day_net_profit,
            'month_total_incomes': month_total_incomes,
            'month_total_expenses': month_total_expenses,
            'month_net_profit': month_net_profit,
            'day_payment_methods': payment_methods,
            'doctor_details': doctor_details,
            'no_doctor_revenue': no_doctor_revenue
        }

        # تحويل التمبليت إلى نص
        email_body = render_to_string('reports/daily_report.html', context)
        email = EmailMessage(
            subject=f'التقرير اليومي - {branch.name} - {today.strftime("%Y-%m-%d")}',
            body=email_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipients or [settings.ADMIN_EMAIL]
        )
        email.content_subtype = 'html'  # إرسال الإيميل كنص HTML
        email.send()

def generate_monthly_report():
    today = timezone.now().date()
    start_date = today.replace(day=1)
    end_date = (start_date + timedelta(days=31)).replace(day=1) - timedelta(days=1)
    branches = Branch.objects.all()
    recipients = ReportRecipient.objects.filter(is_active=True).values_list('email', flat=True)
    for branch in branches:
        branch_payments = Payment.objects.filter(branch=branch, date__date__range=(start_date, end_date))
        total_incomes = branch_payments.aggregate(Sum('amount'))['amount__sum'] or 0
        branch_expenses = Expense.objects.filter(branch=branch, date__range=(start_date, end_date))
        total_expenses = branch_expenses.aggregate(Sum('amount'))['amount__sum'] or 0
        net_profit = total_incomes - total_expenses

        payment_methods = PaymentMethod.objects.filter(
            payment__branch=branch, payment__date__date__range=(start_date, end_date)
        ).annotate(
            total_amount=Sum('payment__amount'), count=Count('payment')
        )

        doctors = Employee.objects.filter(employee_type__name='Doctor', branch=branch)
        doctor_details = []
        for doctor in doctors:
            doctor_revenue = Payment.objects.filter(
                appointment__doctor=doctor, date__date__range=(start_date, end_date)
            ).aggregate(total_revenue=Sum('amount'), count=Count('id'))
            doctor_details.append({
                'name': doctor.name,
                'total_revenue': doctor_revenue['total_revenue'] or 0,
                'count': doctor_revenue['count']
            })

        no_doctor_revenue = Payment.objects.filter(
            appointment__doctor__isnull=True, branch=branch, date__date__range=(start_date, end_date)
        ).aggregate(Sum('amount'))['amount__sum'] or 0

        services = Service.objects.all()
        service_details = []
        for service in services:
            service_revenue = Payment.objects.filter(
                appointment__service=service, branch=branch, date__date__range=(start_date, end_date)
            ).aggregate(total_revenue=Sum('amount'), count=Count('id'))
            service_details.append({
                'name': service.name,
                'total_revenue': service_revenue['total_revenue'] or 0,
                'count': service_revenue['count']
            })

        context = {
            'clinic_name': branch.name,
            'date': start_date.strftime('%Y-%m'),
            'total_incomes': total_incomes,
            'total_expenses': total_expenses,
            'net_profit': net_profit,
            'payment_methods': payment_methods,
            'doctor_details': doctor_details,
            'no_doctor_revenue': no_doctor_revenue,
            'service_details': service_details
        }

        email_body = render_to_string('reports/monthly_report.html', context)
        email = EmailMessage(
            subject=f'التقرير الشهري - {branch.name} - {start_date.strftime("%Y-%m")}',
            body=email_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipients or [settings.ADMIN_EMAIL]
        )
        email.content_subtype = 'html'
        email.send()

def generate_annual_report():
    today = timezone.now().date()
    start_date = today.replace(month=1, day=1)
    end_date = today.replace(month=12, day=31)
    branches = Branch.objects.all()
    recipients = ReportRecipient.objects.filter(is_active=True).values_list('email', flat=True)
    for branch in branches:
        branch_data = []
        for month in range(1, 13):
            month_start = start_date.replace(month=month, day=1)
            month_end = (month_start + timedelta(days=31)).replace(day=1) - timedelta(days=1)
            branch_payments = Payment.objects.filter(branch=branch, date__date__range=(month_start, month_end))
            total_incomes = branch_payments.aggregate(Sum('amount'))['amount__sum'] or 0
            branch_expenses = Expense.objects.filter(branch=branch, date__range=(month_start, month_end))
            total_expenses = branch_expenses.aggregate(Sum('amount'))['amount__sum'] or 0
            net_profit = total_incomes - total_expenses
            branch_data.append({
                'month': f'شهر {month}',
                'total_incomes': total_incomes,
                'total_expenses': total_expenses,
                'net_profit': net_profit
            })
        context = {
            'clinic_name': branch.name,
            'year': start_date.year,
            'branch_data': branch_data
        }
        email_body = render_to_string('reports/annual_report.html', context)
        email = EmailMessage(
            subject=f'التقرير السنوي - {branch.name} - {start_date.year}',
            body=email_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipients or [settings.ADMIN_EMAIL]
        )
        email.content_subtype = 'html'
        email.send()