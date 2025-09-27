from django.shortcuts import render, redirect, get_object_or_404
from .forms import ServiceForm
from .models import Service
from django.conf import settings
from django.contrib import messages
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from utils.utils import export_pdf, export_excel
from datetime import datetime

@login_required
def service_create(request):
    if request.method == 'POST':
        form = ServiceForm(request.POST)
        if form.is_valid():
            service = form.save()
            messages.success(request, f'تم إنشاء الخدمة {service.name} بنجاح')
            return redirect('services:service_list')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = ServiceForm()

    context = {
        'form': form,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'services/create.html', context)

@login_required
def service_list(request):
    context = {
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'services/list.html', context)

@login_required
def service_list_data(request):
    services = Service.objects.all().order_by('name')
    data = [{
        'name': service.name,
        'specialization': service.specialization.name if service.specialization else 'غير محدد',
        'base_price': str(service.base_price),
        'description': service.description or 'غير محدد',
        'actions': f'<a href="{reverse("service_update", args=[service.pk])}" class="btn btn-sm btn-primary">تعديل</a> <a href="{reverse("service_delete", args=[service.pk])}" class="btn btn-sm btn-danger">حذف</a>'
    } for service in services]
    return JsonResponse({'data': data})

@login_required
def service_update(request, pk):
    service = get_object_or_404(Service, pk=pk)
    if request.method == 'POST':
        form = ServiceForm(request.POST, instance=service)
        if form.is_valid():
            form.save()
            messages.success(request, f'تم تعديل الخدمة {service.name} بنجاح')
            return redirect('services:service_list')
        else:
            messages.error(request, 'خطأ في إدخال البيانات')
    else:
        form = ServiceForm(instance=service)

    context = {
        'form': form,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'services/update.html', context)

@login_required
def service_delete(request, pk):
    service = get_object_or_404(Service, pk=pk)
    if request.method == 'POST':
        service.delete()
        messages.success(request, 'تم حذف الخدمة بنجاح')
        return redirect('services:service_list')
    context = {
        'service': service,
        'clinic_name': request.user.branch.name if request.user.branch else getattr(settings, 'CLINIC_NAME', 'Clinic Dashboard'),
        'clinic_logo': request.user.branch.logo.url if request.user.branch and request.user.branch.logo else getattr(settings, 'CLINIC_LOGO', 'images/logo.svg'),
        'footer_text': request.user.branch.footer_text if request.user.branch and request.user.branch.footer_text else getattr(settings, 'FOOTER_TEXT', 'Copyright &copy; 2025 All rights reserved.')
    }
    return render(request, 'services/delete.html', context)

@login_required
def service_list_export(request):
    export_format = request.GET.get('export')
    services = Service.objects.all().order_by('name')
    data = [
        [s.name, s.specialization.name if s.specialization else 'غير محدد', str(s.base_price), s.description or 'غير محدد']
        for s in services
    ]
    headers = ['الاسم', 'التخصص', 'السعر الأساسي', 'الوصف']
    title = 'قائمة الخدمات'
    filename = f'service_list_{datetime.now().strftime("%Y%m%d")}'

    if export_format == 'pdf':
        return export_pdf(data, headers, title, filename)
    elif export_format == 'excel':
        return export_excel(data, headers, title, filename)
    return redirect('services:service_list')