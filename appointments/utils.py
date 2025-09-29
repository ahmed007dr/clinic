from django.utils import timezone
from .models import Appointment

def generate_serial_number(appointment, date=None):
    """
    توليد رقم تذكرة مسلسل بناءً على التاريخ (YYYYMMDD-NNN).
    """
    date = date or appointment.scheduled_date.date()
    base_serial = f"{date.strftime('%Y%m%d')}-"
    existing_count = Appointment.objects.filter(
        scheduled_date__date=date,
        serial_number__startswith=base_serial
    ).count()
    serial = f"{base_serial}{existing_count + 1:03d}"
    
    while Appointment.objects.filter(serial_number=serial).exists():
        existing_count += 1
        serial = f"{base_serial}{existing_count + 1:03d}"
    
    return serial