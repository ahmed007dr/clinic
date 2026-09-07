from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from appointments.models import Appointment
from patients.models import Patient
from billing.models import Payment, Expense
from django.db.models import Sum, Count
from datetime import datetime, timedelta
from django.utils import timezone
@login_required
def dashboard(request):
    today = datetime.now().date()
    week_ago = today - timedelta(days=7)

        # إحصائيات عامة
    total_appointments_today = Appointment.objects.filter(scheduled_date__date=today).count()  # صحيح
    total_patients = Patient.objects.count()

    # إذا كانت الحقول DateField
    total_payments_today = Payment.objects.filter(date=today).aggregate(Sum('amount'))['amount__sum'] or 0
    total_expenses_today = Expense.objects.filter(date=today).aggregate(Sum('amount'))['amount__sum'] or 0

    appointments_by_day = []
    revenue_by_day = []
    expenses_by_day = []

    if request.user.role.name == 'Admin' if request.user.role else False:
        for i in range(7):
            day = today - timedelta(days=i)
            appointments_count = Appointment.objects.filter(scheduled_date__date=day).count()

            revenue = Payment.objects.filter(date=day).aggregate(Sum('amount'))['amount__sum'] or 0
            expense = Expense.objects.filter(date=day).aggregate(Sum('amount'))['amount__sum'] or 0

            appointments_by_day.append(appointments_count)
            revenue_by_day.append(float(revenue))
            expenses_by_day.append(float(expense))

    context = {
        'total_appointments_today': total_appointments_today,
        'total_patients': total_patients,
        'total_payments_today': total_payments_today,
        'total_expenses_today': total_expenses_today,
        'appointments_by_day': appointments_by_day[::-1],
        'revenue_by_day': revenue_by_day[::-1],
        'expenses_by_day': expenses_by_day[::-1],
        'is_reception': request.user.role.name == 'Reception' if request.user.role else False,
    }
    return render(request, 'dashboard/index.html', context)
