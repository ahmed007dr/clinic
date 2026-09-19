"""The times a doctor can be booked, and who sets them (docs/15, Phase 4).

The engine is pure arithmetic over a doctor's week, so it is tested with a fixed
"now"; the endpoints are tested against the real clock with dates worked out
from it.
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from api.tests.test_catalogue import CatalogueBase
from appointments.availability import (
    LEAD_MINUTES, MAX_DAYS_AHEAD, available_days, available_slots, is_offered,
)
from appointments.models import Appointment, BranchHoliday, DoctorSchedule, DoctorTimeOff
from patients.models import Patient
from services.catalog import resolve_offering
from tenants.context import tenant_context
from tenants.models import Tenant
from tenants.provisioning import provision_tenant_defaults

MONDAY = 0
#: A Monday well in the future, so "now" can sit before it.
FIXED_NOW = datetime(2030, 1, 7, 6, 0)  # Monday 06:00
DAY = date(2030, 1, 7)


def hhmm(slots):
    return [s.strftime("%H:%M") for s in slots]


class AvailabilityBase(CatalogueBase):
    """Ahmed works Mondays 09:00–13:00 at Clinic A, break 11:00–11:30; the
    service takes 45 minutes."""

    def setUp(self):
        super().setUp()
        self.week(self.ahmed, self.a, {MONDAY: (time(9), time(13), time(11), time(11, 30))})
        self.patient = Patient.all_objects.create(tenant=self.tenant, name="Pat", branch=self.a)

    def week(self, doctor, branch, days):
        DoctorSchedule.all_objects.filter(doctor=doctor, branch=branch).delete()
        for weekday, (start, end, b_start, b_end) in days.items():
            DoctorSchedule.all_objects.create(
                tenant=self.tenant, doctor=doctor, branch=branch, weekday=weekday,
                start_time=start, end_time=end, break_start=b_start, break_end=b_end,
            )

    def offer(self, branch=None, doctor=None):
        with tenant_context(self.tenant):
            found = resolve_offering(branch or self.a, doctor or self.ahmed, self.laser)
        self.assertIsNotNone(found)
        return found

    def slots(self, day=DAY, now=FIXED_NOW, **kw):
        with tenant_context(self.tenant):
            return hhmm(available_slots(self.offer(**kw), day, now))

    def book(self, status="waiting", at=time(9, 45), service="laser", branch=None, day=DAY):
        return Appointment.all_objects.create(
            tenant=self.tenant, patient=self.patient, doctor=self.ahmed,
            service=self.laser if service == "laser" else None, branch=branch or self.a,
            status=status, scheduled_date=datetime.combine(day, at),
        )


class EngineTests(AvailabilityBase):
    def test_a_day_is_cut_into_service_length_steps_around_the_break(self):
        # 09:00 and 09:45 fit before 11:00 (10:30 would run into the break);
        # the second half starts again at the end of the break.
        self.assertEqual(self.slots(), ["09:00", "09:45", "11:30", "12:15"])

    def test_no_row_for_the_weekday_is_a_day_off(self):
        self.assertEqual(self.slots(day=DAY + timedelta(days=1)), [])

    def test_a_schedule_at_another_clinic_does_not_count_here(self):
        self.week(self.ahmed, self.b, {1: (time(9), time(12), None, None)})
        self.assertEqual(self.slots(day=DAY + timedelta(days=1)), [])

    def test_a_booking_removes_the_times_it_occupies(self):
        self.book(at=time(9, 45))
        self.assertEqual(self.slots(), ["09:00", "11:30", "12:15"])

    def test_a_request_the_clinic_has_not_confirmed_holds_nothing(self):
        for status in ("requested", "cancelled", "no_show"):
            with self.subTest(status=status):
                Appointment.all_objects.all().delete()
                self.book(status=status, at=time(9, 45))
                self.assertEqual(self.slots(), ["09:00", "09:45", "11:30", "12:15"])

    def test_confirmed_and_finished_bookings_hold_the_time(self):
        for status in ("waiting", "called", "entered", "quick", "completed"):
            with self.subTest(status=status):
                Appointment.all_objects.all().delete()
                self.book(status=status, at=time(9, 45))
                self.assertNotIn("09:45", self.slots())

    def test_the_doctor_is_one_person_a_booking_at_another_clinic_blocks_too(self):
        self.book(at=time(9, 45), branch=self.b)
        self.assertNotIn("09:45", self.slots())

    def test_a_booking_with_no_service_counts_as_half_an_hour(self):
        self.book(at=time(11, 30), service=None)  # 11:30–12:00
        self.assertEqual(self.slots(), ["09:00", "09:45", "12:15"])

    def test_time_off_closes_every_clinic_that_day(self):
        DoctorTimeOff.all_objects.create(tenant=self.tenant, doctor=self.ahmed, start_date=DAY, end_date=DAY)
        self.assertEqual(self.slots(), [])
        # ...and only that day.
        self.assertEqual(self.slots(day=DAY + timedelta(days=7)), ["09:00", "09:45", "11:30", "12:15"])

    def test_a_clinic_holiday_closes_that_clinic_only(self):
        BranchHoliday.all_objects.create(tenant=self.tenant, branch=self.a, start_date=DAY, end_date=DAY)
        self.assertEqual(self.slots(), [])
        self.week(self.mohamed, self.b, {MONDAY: (time(9), time(11), None, None)})
        self.assertEqual(self.slots(branch=self.b, doctor=self.mohamed), ["09:00", "09:45"])

    def test_a_group_wide_holiday_closes_everything(self):
        BranchHoliday.all_objects.create(tenant=self.tenant, branch=None, start_date=DAY, end_date=DAY)
        self.assertEqual(self.slots(), [])

    def test_a_run_of_days_covers_each_of_them(self):
        DoctorTimeOff.all_objects.create(
            tenant=self.tenant, doctor=self.ahmed, start_date=DAY - timedelta(days=2), end_date=DAY + timedelta(days=2)
        )
        self.assertEqual(self.slots(), [])

    def test_nothing_sooner_than_the_lead_time_is_offered(self):
        now = datetime.combine(DAY, time(9, 10))
        # 09:10 + 60 min = 10:10: the two morning times are gone, the rest stay.
        self.assertEqual(LEAD_MINUTES, 60)
        self.assertEqual(self.slots(now=now), ["11:30", "12:15"])

    def test_the_past_and_the_far_future_offer_nothing(self):
        self.assertEqual(self.slots(day=DAY - timedelta(days=7)), [])
        far = DAY + timedelta(days=MAX_DAYS_AHEAD + 7)
        self.assertEqual(self.slots(day=far), [])

    def test_a_step_that_would_run_past_closing_is_not_offered(self):
        self.week(self.ahmed, self.a, {MONDAY: (time(9), time(10, 20), None, None)})
        self.assertEqual(self.slots(), ["09:00"])  # 09:45–10:30 would overrun

    def test_days_lists_only_days_that_still_have_a_time(self):
        with tenant_context(self.tenant):
            offer = self.offer()
            days = available_days(offer, first=DAY, days=30, now=FIXED_NOW)
        self.assertEqual([d.weekday() for d in days], [MONDAY] * len(days))
        self.assertEqual(days[0], DAY)
        self.assertEqual(len(days), 5)  # five Mondays in 30 days from Mon 7 Jan
        # Fill the first Monday and it drops out.
        for at in (time(9), time(9, 45), time(11, 30), time(12, 15)):
            self.book(at=at)
        with tenant_context(self.tenant):
            again = available_days(self.offer(), first=DAY, days=30, now=FIXED_NOW)
        self.assertNotIn(DAY, again)

    def test_is_offered_is_what_booking_will_check(self):
        with tenant_context(self.tenant):
            offer = self.offer()
            self.assertTrue(is_offered(offer, datetime.combine(DAY, time(9, 45)), FIXED_NOW))
            self.assertFalse(is_offered(offer, datetime.combine(DAY, time(10, 0)), FIXED_NOW))  # off the grid
            self.assertFalse(is_offered(offer, datetime.combine(DAY, time(11, 0)), FIXED_NOW))  # in the break

    def test_the_schema_refuses_a_break_outside_the_working_hours(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            DoctorSchedule.all_objects.create(
                tenant=self.tenant, doctor=self.sara, branch=self.a, weekday=2,
                start_time=time(9), end_time=time(12), break_start=time(13), break_end=time(14),
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            DoctorSchedule.all_objects.create(
                tenant=self.tenant, doctor=self.sara, branch=self.a, weekday=2,
                start_time=time(12), end_time=time(9),
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            DoctorSchedule.all_objects.create(
                tenant=self.tenant, doctor=self.sara, branch=self.a, weekday=2,
                start_time=time(9), end_time=time(12), break_start=time(10),
            )

    def test_queries_do_not_grow_with_the_days_asked_for(self):
        with tenant_context(self.tenant):
            offer = self.offer()
            with self.assertNumQueries(4):
                available_days(offer, first=DAY, days=30, now=FIXED_NOW)


def next_weekday(weekday, at_least_days=2):
    day = timezone.now().date() + timedelta(days=at_least_days)
    while day.weekday() != weekday:
        day += timedelta(days=1)
    return day


class PublicEndpointTests(AvailabilityBase):
    def setUp(self):
        super().setUp()
        self.day = next_weekday(MONDAY)

    def query(self, **overrides):
        params = {
            "service": str(self.laser.uuid), "branch": str(self.a.uuid), "doctor": str(self.ahmed.uuid),
            "date": self.day.isoformat(),
        }
        params.update(overrides)
        self.client.logout()
        return self.client.get(self.url("catalog-availability"), params)

    def test_it_lists_the_offered_times_without_signing_in(self):
        response = self.query()
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["slots"], ["09:00", "09:45", "11:30", "12:15"])
        self.assertEqual(body["duration_minutes"], 45)

    def test_a_booked_time_disappears_and_reveals_nothing_about_who_booked_it(self):
        self.book(at=time(9, 45), day=self.day)
        body = self.query().json()
        self.assertEqual(body["slots"], ["09:00", "11:30", "12:15"])
        self.assertEqual(set(body), {"date", "duration_minutes", "slots"})

    def test_a_choice_the_clinic_does_not_offer_is_a_404(self):
        self.assertEqual(self.query(doctor=str(self.mohamed.uuid)).status_code, 404)  # not at A
        self.assertEqual(self.query(branch=str(self.c.uuid)).status_code, 404)  # C offers nothing
        self.assertEqual(self.query(service="not-a-uuid").status_code, 404)
        self.assertEqual(self.query(doctor="").status_code, 404)

    def test_a_bad_date_is_refused(self):
        self.assertEqual(self.query(date="tomorrow").status_code, 400)
        self.assertEqual(self.query(date="").status_code, 400)

    def test_days_lists_the_coming_days_with_a_time(self):
        self.client.logout()
        response = self.client.get(self.url("catalog-availability-days"), {
            "service": str(self.laser.uuid), "branch": str(self.a.uuid), "doctor": str(self.ahmed.uuid),
        })
        self.assertEqual(response.status_code, 200)
        days = [date.fromisoformat(d) for d in response.json()["days"]]
        self.assertTrue(days)
        self.assertTrue(all(d.weekday() == MONDAY for d in days))

    def test_switching_the_service_off_stops_offering_times(self):
        self.switch(self.a, is_active=False)
        self.assertEqual(self.query().status_code, 404)

    def test_another_groups_uuids_are_not_found(self):
        rival = Tenant.objects.create(name="Rival", slug="rival-av", status=Tenant.Status.ACTIVE)
        provision_tenant_defaults(rival)
        self.client.logout()
        response = self.client.get(reverse("api:portal:catalog-availability", kwargs={"slug": rival.slug}), {
            "service": str(self.laser.uuid), "branch": str(self.a.uuid), "doctor": str(self.ahmed.uuid),
            "date": self.day.isoformat(),
        })
        self.assertEqual(response.status_code, 404)


class ScheduleEditingTests(AvailabilityBase):
    def get(self, **params):
        return self.client.get(reverse("api:schedules"), params)

    def put(self, **body):
        return self.client.put(reverse("api:schedules"), body, content_type="application/json")

    def days(self, *rows):
        return [
            {"weekday": w, "start_time": s, "end_time": e, **({"break_start": bs, "break_end": be} if bs else {})}
            for w, s, e, bs, be in rows
        ]

    def test_the_owner_reads_a_doctors_week_and_the_clinics_doctors(self):
        self.login("owner")
        body = self.get(branch=self.a.uuid, doctor=self.ahmed.uuid).json()
        self.assertEqual([d["name"] for d in body["doctors"]], ["Dr Ahmed", "Dr Sara"])
        self.assertEqual(body["days"], [
            {"weekday": 0, "start_time": "09:00", "end_time": "13:00", "break_start": "11:00", "break_end": "11:30"}
        ])

    def test_saving_replaces_the_week_and_the_website_follows(self):
        self.login("admin-a")
        response = self.put(
            branch=str(self.a.uuid), doctor=str(self.ahmed.uuid),
            days=self.days((1, "10:00", "12:00", None, None), (3, "09:00", "10:30", "09:45", "10:00")),
        )
        self.assertEqual(response.status_code, 200, response.content)
        weekdays = set(DoctorSchedule.all_objects.filter(doctor=self.ahmed, branch=self.a).values_list("weekday", flat=True))
        self.assertEqual(weekdays, {1, 3})  # Monday was not listed: now a day off
        day = next_weekday(1)
        self.client.logout()
        offered = self.client.get(self.url("catalog-availability"), {
            "service": str(self.laser.uuid), "branch": str(self.a.uuid), "doctor": str(self.ahmed.uuid),
            "date": day.isoformat(),
        }).json()["slots"]
        self.assertEqual(offered, ["10:00", "10:45"])

    def test_an_empty_week_takes_the_doctor_off_the_calendar(self):
        self.login("owner")
        self.assertEqual(self.put(branch=str(self.a.uuid), doctor=str(self.ahmed.uuid), days=[]).status_code, 200)
        self.assertFalse(DoctorSchedule.all_objects.filter(doctor=self.ahmed).exists())

    def test_bad_hours_are_refused(self):
        self.login("owner")
        for rows in (
            [(0, "12:00", "09:00", None, None)],            # ends before it starts
            [(0, "09:00", "12:00", "13:00", "14:00")],      # break outside the day
            [(0, "09:00", "12:00", "10:00", "10:00")],      # empty break
            [(0, "09:00", "12:00", None, None), (0, "13:00", "15:00", None, None)],  # weekday twice
            [(9, "09:00", "12:00", None, None)],            # no such weekday
        ):
            with self.subTest(rows=rows):
                response = self.put(branch=str(self.a.uuid), doctor=str(self.ahmed.uuid), days=self.days(*rows))
                self.assertEqual(response.status_code, 400)
        self.assertTrue(DoctorSchedule.all_objects.filter(doctor=self.ahmed).exists())  # untouched

    def test_a_half_a_break_is_refused(self):
        self.login("owner")
        response = self.put(
            branch=str(self.a.uuid), doctor=str(self.ahmed.uuid),
            days=[{"weekday": 0, "start_time": "09:00", "end_time": "12:00", "break_start": "10:00"}],
        )
        self.assertEqual(response.status_code, 400)

    def test_an_admin_manages_their_own_clinic_only(self):
        self.login("admin-a")
        self.assertEqual([b["name"] for b in self.get().json()["branches"]], ["Clinic A"])
        self.assertEqual(self.get(branch=self.b.uuid).status_code, 404)
        self.assertEqual(self.put(branch=str(self.b.uuid), doctor=str(self.mohamed.uuid), days=[]).status_code, 404)

    def test_a_doctor_who_does_not_work_at_the_clinic_is_not_found(self):
        self.login("owner")
        self.assertEqual(self.put(branch=str(self.a.uuid), doctor=str(self.mohamed.uuid), days=[]).status_code, 404)
        self.assertEqual(self.get(branch=self.a.uuid, doctor=self.mohamed.uuid).status_code, 404)

    def test_a_visiting_doctor_has_a_week_at_each_clinic(self):
        visitor = self.doctor("Dr Visit", "N7", self.a, price="700", extra=[self.b])
        self.login("owner")
        response = self.put(branch=str(self.b.uuid), doctor=str(visitor.uuid), days=self.days((2, "09:00", "12:00", None, None)))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(DoctorSchedule.all_objects.filter(doctor=visitor, branch=self.b, weekday=2).exists())

    def test_reception_is_refused(self):
        self.login("rec")
        self.assertEqual(self.get().status_code, 403)
        self.assertEqual(self.put(branch=str(self.a.uuid), doctor=str(self.ahmed.uuid), days=[]).status_code, 403)


class TimeOffAndHolidayTests(AvailabilityBase):
    def json(self, method, url, body):
        return getattr(self.client, method)(url, body, content_type="application/json")

    def test_an_admin_records_leave_for_a_doctor_of_their_clinic(self):
        self.login("admin-a")
        response = self.json("post", reverse("api:doctortimeoff-list"), {
            "doctor": str(self.ahmed.uuid), "start_date": "2030-02-01", "end_date": "2030-02-03", "reason": "Conference",
        })
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["doctor_name"], "Dr Ahmed")

    def test_an_admin_cannot_book_another_clinics_doctor_off(self):
        self.login("admin-a")
        response = self.json("post", reverse("api:doctortimeoff-list"), {
            "doctor": str(self.mohamed.uuid), "start_date": "2030-02-01", "end_date": "2030-02-03",
        })
        self.assertEqual(response.status_code, 400)
        theirs = DoctorTimeOff.all_objects.create(
            tenant=self.tenant, doctor=self.mohamed, start_date=DAY, end_date=DAY, reason="secret reason",
        )
        listing = self.client.get(reverse("api:doctortimeoff-list")).json()["results"]
        self.assertNotIn(str(theirs.uuid), str(listing))
        self.assertEqual(self.client.get(reverse("api:doctortimeoff-detail", args=[theirs.uuid])).status_code, 404)

    def test_a_backwards_range_is_refused(self):
        self.login("owner")
        response = self.json("post", reverse("api:doctortimeoff-list"), {
            "doctor": str(self.ahmed.uuid), "start_date": "2030-02-03", "end_date": "2030-02-01",
        })
        self.assertEqual(response.status_code, 400)

    def test_the_reason_is_never_public(self):
        DoctorTimeOff.all_objects.create(tenant=self.tenant, doctor=self.ahmed, start_date=DAY, end_date=DAY, reason="Surgery")
        self.client.logout()
        body = self.client.get(self.url("catalog-services")).content.decode() + self.doctors(self.a).content.decode()
        self.assertNotIn("Surgery", body)

    def test_reception_cannot_manage_leave_or_holidays(self):
        self.login("rec")
        self.assertEqual(self.client.get(reverse("api:doctortimeoff-list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("api:branchholiday-list")).status_code, 403)

    def test_the_owner_closes_the_whole_group_and_an_admin_cannot(self):
        self.login("owner")
        group = self.json("post", reverse("api:branchholiday-list"), {
            "start_date": "2030-05-01", "end_date": "2030-05-01", "name": "Labour Day",
        })
        self.assertEqual(group.status_code, 201, group.content)
        self.login("admin-a")
        refused = self.json("post", reverse("api:branchholiday-list"), {"start_date": "2030-05-02", "end_date": "2030-05-02"})
        self.assertEqual(refused.status_code, 400)

    def test_an_admin_closes_their_own_clinic_and_no_other(self):
        self.login("admin-a")
        own = self.json("post", reverse("api:branchholiday-list"), {
            "branch": str(self.a.uuid), "start_date": "2030-05-02", "end_date": "2030-05-03", "name": "Renovation",
        })
        self.assertEqual(own.status_code, 201, own.content)
        other = self.json("post", reverse("api:branchholiday-list"), {
            "branch": str(self.b.uuid), "start_date": "2030-05-02", "end_date": "2030-05-03",
        })
        self.assertEqual(other.status_code, 400)

    def test_an_admin_sees_group_days_but_cannot_change_or_remove_them(self):
        group = BranchHoliday.all_objects.create(tenant=self.tenant, branch=None, start_date=DAY, end_date=DAY, name="Eid")
        elsewhere = BranchHoliday.all_objects.create(tenant=self.tenant, branch=self.b, start_date=DAY, end_date=DAY, name="B only")
        self.login("admin-a")
        names = [row["name"] for row in self.client.get(reverse("api:branchholiday-list")).json()["results"]]
        self.assertEqual(names, ["Eid"])
        self.assertEqual(self.client.delete(reverse("api:branchholiday-detail", args=[group.uuid])).status_code, 403)
        self.assertEqual(self.json("patch", reverse("api:branchholiday-detail", args=[group.uuid]), {"name": "x"}).status_code, 400)
        self.assertEqual(self.client.delete(reverse("api:branchholiday-detail", args=[elsewhere.uuid])).status_code, 404)
        self.assertEqual(BranchHoliday.all_objects.count(), 2)
