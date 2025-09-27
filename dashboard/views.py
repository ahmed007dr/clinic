from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from appointments.models import Appointment
from patients.models import Patient
from billing.models import Payment, Expense
from django.conf import settings
from django.db.models import Sum, Count
from datetime import datetime, timedelta
from django.utils import timezone

@login_required
def dashboard(request):
    today = datetime.now().date()
    week_ago = today - timedelta(days=7)

    # إحصائيات عامة
    total_appointments_today = Appointment.objects.filter(scheduled_date__date=today).count()
    total_patients = Patient.objects.count()
    total_payments_today = Payment.objects.filter(date__date=today).aggregate(Sum('amount'))['amount__sum'] or 0
    total_expenses_today = Expense.objects.filter(date__date=today).aggregate(Sum('amount'))['amount__sum'] or 0

    # إحصائيات للرسوم البيانية (للأدمن فقط)
    appointments_by_day = []
    revenue_by_day = []
    expenses_by_day = []
    if request.user.role.name == 'Admin' if request.user.role else False:
        for i in range(7):
            day = today - timedelta(days=i)
            appointments_count = Appointment.objects.filter(scheduled_date__date=day).count()
            revenue = Payment.objects.filter(date__date=day).aggregate(Sum('amount'))['amount__sum'] or 0
            expenses = Expense.objects.filter(date__date=day).aggregate(Sum('amount'))['amount__sum'] or 0
            appointments_by_day.append(appointments_count)
            revenue_by_day.append(float(revenue))
            expenses_by_day.append(float(expenses))

    context = {
        'total_appointments_today': total_appointments_today,
        'total_patients': total_patients,
        'total_payments_today': total_payments_today,
        'total_expenses_today': total_expenses_today,
        'appointments_by_day': appointments_by_day[::-1],  # عكس الترتيب للرسم البياني
        'revenue_by_day': revenue_by_day[::-1],
        'expenses_by_day': expenses_by_day[::-1],
        'is_reception': request.user.role.name == 'Reception' if request.user.role else False,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'dashboard/index.html', context)