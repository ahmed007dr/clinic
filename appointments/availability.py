"""The times a doctor can be booked — what the customer may choose from (docs/15, Phase 4).

For one bookable choice (`services.catalog.Offering`: clinic, doctor, service) and
one day, the offered times are the doctor's working hours at that clinic on that
weekday, cut into steps of the service's duration, **minus**:

* the break (a step that touches it is dropped; the second half of the day starts
  again from the end of the break);
* the doctor's time off, and the clinic's — or the whole group's — holidays;
* bookings that already occupy the doctor, at *any* clinic (a doctor is in one
  place at a time), counted from `scheduled_date` for the length of the service
  they were booked for. A request that reception has not confirmed
  (`requested`) holds nothing (docs/15, D4), and nor do cancelled or missed ones;
* anything sooner than `LEAD_MINUTES` from now, and anything past `MAX_DAYS_AHEAD`.

Nothing here writes. Booking re-asks `available_slots` for the exact time before
creating anything, so a stale page can never book a time that has gone.

The project runs with `USE_TZ = False` (clinic-local time), so every datetime
here is naive local time, like `Appointment.scheduled_date`.
"""

from datetime import date, datetime, timedelta

from django.utils import timezone

from .models import Appointment, BranchHoliday, DoctorSchedule, DoctorTimeOff

#: A booking in one of these occupies the doctor. `requested` does not (D4).
BLOCKING = ("waiting", "called", "entered", "quick", "completed")
MAX_DAYS_AHEAD = 60
LEAD_MINUTES = 60
#: A booking with no service (a walk-in) is treated as this long.
DEFAULT_MINUTES = 30


def _covers(ranges, day):
    return any(start <= day <= end for start, end in ranges)


class Calendar:
    """What is needed to work out days `first`..`last` for one choice, loaded
    once so a range of days costs the same handful of queries as one day."""

    def __init__(self, offering, first, last):
        self.offering = offering
        self.duration = timedelta(minutes=offering.service.duration_minutes)
        doctor, branch = offering.doctor, offering.branch

        self.schedule = {
            row.weekday: row
            for row in DoctorSchedule.objects.filter(doctor=doctor, branch=branch, is_active=True)
        }
        self.time_off = [
            (row.start_date, row.end_date)
            for row in DoctorTimeOff.objects.filter(doctor=doctor, end_date__gte=first, start_date__lte=last)
        ]
        self.holidays = [
            (row.start_date, row.end_date)
            for row in BranchHoliday.objects.filter(end_date__gte=first, start_date__lte=last)
            if row.branch_id in (None, branch.pk)
        ]
        window_start = datetime.combine(first, datetime.min.time()) - timedelta(days=1)
        window_end = datetime.combine(last, datetime.min.time()) + timedelta(days=2)
        self.booked = [
            (a.scheduled_date, a.scheduled_date + timedelta(
                minutes=a.service.duration_minutes if a.service_id else DEFAULT_MINUTES))
            for a in Appointment.objects.filter(
                doctor=doctor, status__in=BLOCKING,
                scheduled_date__gte=window_start, scheduled_date__lt=window_end,
            ).select_related("service")
        ]

    def _free(self, start, end):
        return not any(start < b_end and end > b_start for b_start, b_end in self.booked)

    def slots(self, day, now=None):
        """Naive local datetimes a booking may start at on `day`, in order."""
        now = now or timezone.now()
        if day < now.date() or day > now.date() + timedelta(days=MAX_DAYS_AHEAD):
            return []
        row = self.schedule.get(day.weekday())
        if row is None or _covers(self.time_off, day) or _covers(self.holidays, day):
            return []

        def at(t):
            return datetime.combine(day, t)

        segments = [(at(row.start_time), at(row.end_time))]
        if row.break_start is not None:
            segments = [(at(row.start_time), at(row.break_start)), (at(row.break_end), at(row.end_time))]

        earliest = now + timedelta(minutes=LEAD_MINUTES)
        found = []
        for begin, finish in segments:
            start = begin
            while start + self.duration <= finish:
                if start >= earliest and self._free(start, start + self.duration):
                    found.append(start)
                start += self.duration
        return found


def available_slots(offering, day, now=None):
    """The start times offered on one day."""
    return Calendar(offering, day, day).slots(day, now)


def available_days(offering, first=None, days=30, now=None):
    """`[date]` in the next `days` days that still have at least one time."""
    now = now or timezone.now()
    first = first or now.date()
    last = min(first + timedelta(days=days - 1), now.date() + timedelta(days=MAX_DAYS_AHEAD))
    calendar = Calendar(offering, first, last)
    result, day = [], first
    while day <= last:
        if calendar.slots(day, now):
            result.append(day)
        day += timedelta(days=1)
    return result


def is_offered(offering, when, now=None):
    """Whether `when` (a naive local datetime) is one of the offered times —
    the check booking makes on the server."""
    return when in available_slots(offering, when.date(), now)


def parse_day(text):
    """A `YYYY-MM-DD` string as a date, or None."""
    try:
        return date.fromisoformat(str(text))
    except ValueError:
        return None
