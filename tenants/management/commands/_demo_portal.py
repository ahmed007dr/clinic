"""Demo data for the public portal and online booking (docs/15).

Called by `seed_demo` once a group's clinics, doctors, services and patients
exist. It adds what the public directory, the group's page, the catalogue and
the booking journey need to show something real — and what the staff screens
built around them (requests from the website, quantity in the room, the online
shift) need to have on them:

* the group is **listed in the public directory**, with a logo and cover; one
  clinic's own images are approved, another's are waiting for the Owner;
* services with durations and price display, by the piece (pulses), by the
  millilitre with the doctor deciding in the room, and "after evaluation";
  each clinic offers a chosen set (one clinic does not offer one of them);
* doctors shown publicly with an approved line and links, weekly schedules with
  a break, a doctor's leave and clinic holidays;
* bookings from the website in every state: a request awaiting the clinic's
  call, an instant-confirmed one, a reschedule request, a cancelled one, one by
  quantity, a visiting patient at another clinic;
* online payments gathered in the clinic's **online shift** (one closed, one
  open); and a patient in the room whose quantity the doctor still has to fix.

Everything is written through the models the API uses, and the times of
website bookings are picked from what the availability engine really offers.
"""

import io
import random
from datetime import time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.utils import timezone
from PIL import Image, ImageDraw

from appointments.availability import available_days, available_slots
from appointments.models import Appointment, BranchHoliday, DoctorSchedule, DoctorTimeOff
from billing.models import CashShift, DoctorServiceRate, Payment, PaymentMethod
from billing.pricing import quantity_total
from billing.shifts import online_shift, summarize
from employees.models import Employee, Specialization
from notifications.models import Notification
from patients.models import Patient
from services.catalog import offerings
from services.models import BranchService, Service
from tenants.models import SerialCounter, Tenant

# Sat, Sun, Mon, Tue, Wed, Thu — Friday is the weekly day off (Python: Monday = 0).
WORKING_DAYS = (5, 6, 0, 1, 2, 3)

# (name, description, base price, minutes, price display, extra fields)
PORTAL_SERVICES = [
    ("ليزر بالنبضة", "جلسة ليزر تُحسب بعدد النبضات — السعر المكتوب لكل نبضة.", 3, 30, "fixed",
     dict(requires_quantity=True, quantity_unit="نبضة", min_quantity=Decimal("50"), max_quantity=Decimal("800"))),
    ("حقن فيلر", "تُحسب بالملّي — والطبيب يحدد الكمية الفعلية داخل الغرفة.", 1800, 45, "starting_from",
     dict(requires_quantity=True, doctor_sets_quantity=True, quantity_unit="مل",
          min_quantity=Decimal("1"), max_quantity=Decimal("10"))),
    ("استشارة تجميل", "يحدد الطبيب السعر بعد تقييم الحالة.", 500, 30, "after_evaluation", {}),
]

# Minutes per session and how the price is told, for the services the seeder already makes.
KNOWN_SERVICES = {
    "Eximer 120": (40, "fixed"), "Eximer 160": (45, "fixed"), "Q switch 800": (30, "starting_from"),
    "كشف عام": (20, "fixed"), "استشارة جلدية": (20, "fixed"), "تنظيف بشرة": (60, "starting_from"),
}

TAGLINES = [
    "استشاري الأمراض الجلدية والتناسلية والليزر",
    "أخصائي التجميل وعلاج التصبغات",
    "مدرّس الأمراض الجلدية — جامعة القاهرة",
    "أخصائي الجلدية والحساسية",
]

PUBLIC_ABOUT = {
    "dr-ahmed": "مجمع طبي متخصص في الجلدية والليزر بأحدث الأجهزة، بفرعين في سوهاج وأسيوط.",
    "nile-clinic": "عيادة استشارات جلدية وعناية بالبشرة في قلب القاهرة.",
}

BRAND = {
    "dr-ahmed": ((16, 94, 122), (232, 246, 250)),
    "nile-clinic": ((46, 110, 78), (236, 247, 240)),
}


def _picture(size, color, paper, label=""):
    """A plain placeholder image (PNG bytes): a colour field with a simple mark."""
    image = Image.new("RGB", size, paper)
    draw = ImageDraw.Draw(image)
    width, height = size
    if width > height * 2:  # a cover: soft bands
        for band in range(4):
            top = int(height * (0.15 + band * 0.22))
            draw.rectangle([0, top, width, top + int(height * 0.09)], fill=tuple(int(c * 0.35 + p * 0.65) for c, p in zip(color, paper)))
    else:  # a logo: a disc with a cross
        margin = int(width * 0.12)
        draw.ellipse([margin, margin, width - margin, height - margin], fill=color)
        centre, arm, thick = width // 2, int(width * 0.24), int(width * 0.07)
        draw.rectangle([centre - thick, centre - arm, centre + thick, centre + arm], fill=paper)
        draw.rectangle([centre - arm, centre - thick, centre + arm, centre + thick], fill=paper)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return ContentFile(buffer.getvalue())


def _set_images(target, prefix, slug, *, tone):
    color, paper = tone
    getattr(target, f"{prefix}logo").save(f"{slug}-logo.png", _picture((256, 256), color, paper), save=False)
    getattr(target, f"{prefix}cover").save(f"{slug}-cover.png", _picture((1400, 420), color, paper), save=False)


def seed_public_portal(command, tenant, branches, users, doctors, services, specializations, payment_methods):
    """Everything above, inside the group's tenant context. Returns a summary dict."""
    owner, clinic_admin, reception, demo_user = users[0], users[1], users[2], users[3]
    demo_doctor = demo_user.employee
    now = timezone.now()
    today = now.date()
    slug = tenant.slug
    tone = BRAND.get(slug, ((16, 94, 122), (232, 246, 250)))
    multi = len(branches) > 1

    # ---- the group: found in the directory, open to self-registration
    tenant.listed_in_directory = True
    tenant.portal_self_registration = True
    tenant.portal_allow_other_branches = multi  # the visiting-patient rule needs two clinics
    _set_images(tenant, "public_", slug, tone=tone)
    tenant.save()

    # ---- clinics: public details, links, images and booking rules
    for index, branch in enumerate(branches):
        branch.about_visible = True
        branch.about_text = PUBLIC_ABOUT.get(slug, branch.about_text)
        branch.print_links = {
            "whatsapp": f"2010990000{index}{index + 1}",
            "facebook": f"https://facebook.com/{slug}.{branch.code.lower()}",
            "instagram": f"https://instagram.com/{slug}.{branch.code.lower()}",
        }
        # The second clinic confirms website bookings at once; the first phones the customer.
        branch.online_booking_confirms_at_once = index == 1
        branch.online_cancel_notice_hours = 24
        if index == 0:
            _set_images(branch, "public_", f"{slug}-{branch.code.lower()}", tone=tone)  # approved
        else:
            # Uploaded by this clinic's Admin, waiting for the Owner's approval.
            branch.pending_public_logo.save(
                f"{slug}-{branch.code.lower()}-logo.png", _picture((256, 256), tone[0], tone[1]), save=False)
            branch.media_status = "pending"
        branch.save()

    # ---- services: durations, price display, and the by-quantity ones
    for service in services:
        minutes, display = KNOWN_SERVICES.get(service.name, (30, "fixed"))
        service.duration_minutes, service.price_display = minutes, display
        service.save(update_fields=["duration_minutes", "price_display"])
    everything = list(services)
    for name, description, price, minutes, display, extra in PORTAL_SERVICES:
        service, _ = Service.objects.update_or_create(
            tenant=tenant, name=name,
            defaults=dict(
                description=description, base_price=Decimal(price), duration_minutes=minutes,
                price_display=display, specialization=random.choice(specializations), **extra,
            ),
        )
        everything.append(service)
    by_name = {s.name: s for s in everything}

    # ---- doctors: who is shown, their approved line, where they work, what they charge
    doctors = [d for d in doctors]
    for index, doctor in enumerate(doctors):
        # The last doctor stays private: appearing publicly is management's choice, per doctor.
        doctor.show_publicly = index < len(doctors) - 1 or len(doctors) < 3
        doctor.public_profile = {
            "tagline": TAGLINES[index % len(TAGLINES)],
            "links": {"facebook": f"https://facebook.com/{slug}.dr{index + 1}"},
        }
        doctor.profile_status = "approved"
        doctor.profile_reviewed_by = clinic_admin
        doctor.profile_reviewed_at = now
        doctor.save()
    if multi and len(doctors) > 1:
        # Linked to a second clinic by the Owner — the doctor works in both.
        other = next(b for b in branches if b.pk != doctors[1].branch_id)
        doctors[1].extra_branches.add(other)

    # Contracts for the new services; a few doctors charge a little more.
    for index, doctor in enumerate(doctors):
        for service in everything:
            price = None
            if service.name in {s[0] for s in PORTAL_SERVICES}:
                if service.price_display != "after_evaluation":
                    price = (service.base_price * (Decimal("1") + Decimal("0.1") * (index % 3))).quantize(Decimal("0.01"))
            elif index % 3 == 1 and service.name in ("Eximer 120", "استشارة جلدية"):
                price = (service.base_price * Decimal("1.2")).quantize(Decimal("0.01"))
            DoctorServiceRate.objects.update_or_create(
                tenant=tenant, doctor=doctor, service=service,
                defaults={"price": price, "commission_percent": Decimal("40"), "is_active": True},
            )

    # ---- which clinic offers what (one clinic does not offer one of the services)
    for branch_index, branch in enumerate(branches):
        for service in everything:
            offered = not (multi and branch_index == 1 and service.name == "Q switch 800")
            BranchService.objects.update_or_create(
                tenant=tenant, branch=branch, service=service,
                defaults={
                    "is_active": offered,
                    # Offered, but the clinic wants a phone call before booking it.
                    "online_bookable": not (branch_index == 0 and service.name == "Eximer 160"),
                },
            )

    # ---- weekly schedules, a doctor's leave, clinic holidays
    schedules = 0
    for index, doctor in enumerate(doctors):
        for branch in [b for b in branches if b.pk == doctor.branch_id or doctor.extra_branches.filter(pk=b.pk).exists()]:
            for weekday in WORKING_DAYS[: 6 if index % 2 == 0 else 4]:
                DoctorSchedule.objects.update_or_create(
                    tenant=tenant, doctor=doctor, branch=branch, weekday=weekday,
                    defaults=dict(
                        start_time=time(9, 0), end_time=time(17, 0) if index % 2 == 0 else time(15, 0),
                        break_start=time(13, 0) if index % 2 == 0 else None,
                        break_end=time(14, 0) if index % 2 == 0 else None, is_active=True,
                    ),
                )
                schedules += 1
    DoctorTimeOff.objects.update_or_create(
        tenant=tenant, doctor=doctors[0], start_date=today + timedelta(days=10),
        defaults=dict(end_date=today + timedelta(days=12), reason="مؤتمر علمي"),
    )
    BranchHoliday.objects.update_or_create(
        tenant=tenant, branch=None, start_date=today + timedelta(days=20),
        defaults=dict(end_date=today + timedelta(days=20), name="إجازة رسمية — كل العيادات"),
    )
    BranchHoliday.objects.update_or_create(
        tenant=tenant, branch=branches[0], start_date=today + timedelta(days=8),
        defaults=dict(end_date=today + timedelta(days=8), name="صيانة الأجهزة"),
    )

    # ---- where the older demo bookings came from
    for appointment in Appointment.objects.filter(source=Appointment.Source.RECEPTION):
        source = random.choices(
            [Appointment.Source.RECEPTION, Appointment.Source.PHONE, Appointment.Source.WHATSAPP, Appointment.Source.ADMIN],
            weights=[55, 25, 15, 5],
        )[0]
        if source != Appointment.Source.RECEPTION:
            Appointment.all_objects.filter(pk=appointment.pk).update(source=source)

    portal = _website_bookings(
        tenant, branches, doctors, by_name, payment_methods, owner, reception, demo_user, now,
    )
    quantity = _doctor_sizes_the_quantity(tenant, branches[0], demo_doctor, by_name, reception, now)

    return {
        "listed": True, "schedules": schedules, "services": len(everything),
        "branch_offers": BranchService.objects.filter(is_active=True).count(), **portal, **quantity,
    }


# ---------------------------------------------------------------------- bookings


def _first_slot(offer, skip=0):
    """A really offered time for this (clinic, doctor, service), or None."""
    for day in available_days(offer, days=30):
        times = available_slots(offer, day)
        if len(times) > skip:
            return times[skip]
    return None


def _website_booking(tenant, patient, offer, status, when, *, quantity=None, notes="", estimate=False, **extra):
    unit = offer.price
    price = quantity_total(unit, quantity) if quantity is not None else (unit or 0)
    return Appointment.objects.create(
        tenant=tenant, patient=patient, branch=offer.branch, doctor=offer.doctor, service=offer.service,
        specialization=offer.service.specialization, status=status, scheduled_date=when,
        price=price, quantity=quantity, unit_price=unit if quantity is not None else None,
        quantity_is_estimate=estimate, source=Appointment.Source.PUBLIC_PORTAL,
        notes=f"[طلب من بوابة المرضى] {notes}".strip(), **extra,
    )


def _website_bookings(tenant, branches, doctors, by_name, payment_methods, owner, reception, demo_user, now):
    """Website bookings in every state, for the two portal demo patients."""
    sara = Patient.objects.filter(phone1="01099000003").first()
    if sara is None:
        return {"website_bookings": 0, "online_payments": 0}
    mona = khaled = sara  # one website customer, so the other two demo portals stay as they are
    first, last = branches[0], branches[-1]
    made = []
    # The two groups sell different things: a simple consultation and a longer session of each.
    basic = "كشف عام" if "كشف عام" in by_name else "استشارة جلدية"
    session = "Eximer 120" if "Eximer 120" in by_name else "تنظيف بشرة"

    # The old seed left one request without a source: it came from the website.
    Appointment.objects.filter(patient__phone1="01099000001", status="requested").update(
        source=Appointment.Source.PUBLIC_PORTAL)

    def pick(branch, service_name, skip=0):
        service = by_name[service_name]
        for offer in offerings(service=service, branch=branch):
            when = _first_slot(offer, skip)
            if when is not None:
                return offer, when
        return None, None

    # 1. A request from a new customer: holds no time, the clinic phones them.
    offer, when = pick(first, basic)
    if offer is not None:
        made.append(_website_booking(tenant, khaled, offer, "requested", when, notes="أول زيارة — أرجو الاتصال لتحديد الموعد"))

    # 2. A request with a reschedule wish on a confirmed booking.
    offer, when = pick(first, session, skip=1)
    if offer is not None:
        wanted = _first_slot(offer, 3) or (when + timedelta(days=1))
        made.append(_website_booking(
            tenant, mona, offer, "waiting", when, notes="جلسة متابعة",
            reschedule_requested_for=wanted, reschedule_note="أفضّل وقتاً بعد الظهر",
        ))

    # 3. Booked at another clinic of the group — a visiting patient there.
    if last.pk != first.pk:
        offer, when = pick(last, "استشارة تجميل")
        if offer is not None:
            made.append(_website_booking(tenant, mona, offer, "waiting", when, notes="حجز فوري في الفرع الآخر"))

    # 4. By quantity: pulses, asked for by the customer; the total is unit × quantity.
    offer, when = pick(first, "ليزر بالنبضة")
    if offer is not None:
        made.append(_website_booking(tenant, khaled, offer, "requested", when, quantity=Decimal("200"), notes="منطقة الساقين"))

    # 5. One the customer cancelled.
    offer, when = pick(first, basic, skip=2)
    if offer is not None:
        made.append(_website_booking(tenant, mona, offer, "cancelled", when, notes="ألغيت من الموقع"))

    # 6. Confirmed and paid online: the money sits in the clinic's online shift.
    online = 0
    method, _ = PaymentMethod.objects.get_or_create(tenant=tenant, name="دفع إلكتروني")
    paid_offer, paid_when = pick(last, session, skip=1)
    if paid_offer is not None and (paid_offer.price or 0) > 0:
        appointment = _website_booking(tenant, mona, paid_offer, "waiting", paid_when, notes="دفع أونلاين")
        made.append(appointment)
        online += _online_payments(tenant, appointment, method, owner, now)

    # In-app notice for the desk: the requests waiting for a call.
    for appointment in made:
        if appointment.status == "requested":
            for user in (reception, get_user_model().objects.filter(tenant=tenant, role__name="Admin").first()):
                if user is not None:
                    Notification.objects.create(
                        tenant=tenant, user=user, type="appointment", title="طلب موعد جديد من الموقع",
                        message=f"{appointment.patient.name} — {appointment.service.name} — "
                                f"{appointment.scheduled_date:%Y-%m-%d %H:%M}. اتصل بالعميل لتأكيد الموعد.",
                    )
    return {"website_bookings": len(made), "online_payments": online}


def _online_payments(tenant, appointment, method, owner, now):
    """One earlier online shift, already closed by management with its payment,
    and today's open one holding the payment for `appointment`."""
    branch_id = appointment.branch_id
    cent = Decimal("0.01")

    # Yesterday's: a small older booking paid online, then the shift closed and frozen.
    earlier = CashShift.objects.create(
        tenant=tenant, branch_id=branch_id, kind=CashShift.Kind.ONLINE, user=None,
        notes="وردية الدفع الإلكتروني — تُفتح تلقائياً وتُغلق بمراجعة الإدارة.",
    )
    yesterday = now - timedelta(days=1)
    old = Appointment.objects.create(
        tenant=tenant, patient=appointment.patient, branch_id=branch_id, doctor=appointment.doctor,
        service=appointment.service, specialization=appointment.specialization, status="completed",
        scheduled_date=yesterday, price=appointment.price, source=Appointment.Source.PUBLIC_PORTAL,
        notes="[طلب من بوابة المرضى] دفع أونلاين",
    )
    Payment.objects.create(
        tenant=tenant, appointment=old, patient=old.patient, method=method, branch_id=branch_id, shift=earlier,
        receipt_number="R-" + SerialCounter.next_serial(tenant.id, "receipt", yesterday.date()),
        amount=Decimal(old.price).quantize(cent), notes="دفع إلكتروني — بطاقة — مرجع البوابة demo-0001",
    )
    CashShift.all_objects.filter(pk=earlier.pk).update(opened_at=yesterday - timedelta(hours=2))
    earlier.refresh_from_db()
    CashShift.all_objects.filter(pk=earlier.pk).update(
        status=CashShift.Status.CLOSED, closed_at=yesterday + timedelta(hours=8), closed_by=owner,
        closing_summary=summarize(earlier),
    )

    # Today's: the payment for the new booking, recorded inside the open online shift.
    shift = online_shift(tenant, branch_id)
    Payment.objects.create(
        tenant=tenant, appointment=appointment, patient=appointment.patient, method=method,
        branch_id=branch_id, shift=shift,
        receipt_number="R-" + SerialCounter.next_serial(tenant.id, "receipt", now.date()),
        amount=Decimal(appointment.price).quantize(cent),
        notes="دفع إلكتروني — بطاقة — مرجع البوابة demo-0002",
    )
    return 2


def _doctor_sizes_the_quantity(tenant, branch, doctor, by_name, reception, now):
    """A patient in the doctor's room for a service the doctor sizes: booked on an
    estimate (the smallest quantity), paid for it, and waiting for the real figure."""
    service = by_name["حقن فيلر"]
    patient = Patient.objects.filter(tenant=tenant, branch=branch).exclude(phone1__in=["01099000001", "01099000002"]).first()
    rate = DoctorServiceRate.objects.filter(tenant=tenant, doctor=doctor, service=service).first()
    shift = CashShift.objects.filter(user=reception, branch=branch, status=CashShift.Status.OPEN).first()
    if patient is None or rate is None or shift is None:
        return {"doctor_sizes": 0}
    unit = rate.price or service.base_price
    estimate = service.min_quantity
    appointment = Appointment.objects.create(
        tenant=tenant, patient=patient, doctor=doctor, branch=branch, service=service,
        specialization=service.specialization, status="waiting", scheduled_date=now - timedelta(minutes=5),
        quantity=estimate, unit_price=unit, quantity_is_estimate=True, price=quantity_total(unit, estimate),
        source=Appointment.Source.RECEPTION, created_by=reception, notes="الطبيب يحدد الكمية داخل الغرفة",
    )
    Payment.objects.create(
        tenant=tenant, appointment=appointment, patient=patient, method=PaymentMethod.objects.filter(tenant=tenant).first(),
        branch=branch, shift=shift, created_by=reception,
        receipt_number="R-" + SerialCounter.next_serial(tenant.id, "receipt", now.date()),
        amount=Decimal(appointment.price).quantize(Decimal("0.01")),
    )
    # Paid in full, so the patient may go in — which opens the visit.
    appointment.status = "entered"
    appointment.save(update_fields=["status"])
    return {"doctor_sizes": 1}
