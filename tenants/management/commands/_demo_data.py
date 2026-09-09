"""A Faker stand-in, so demo data can be seeded on a production install.

`Faker` is a development dependency: it exists to generate fixtures and has no
business being installed on a server that holds patient records. But the demo
dataset is what the system is delivered with, which means `seed_demo` has to run
*there* — and a seeder that needs a dev-only package to run cannot.

Rather than push Faker into production requirements, this provides the seven
methods the seeder actually calls, backed by Arabic word lists. Faker is still
used when present (it produces more varied data for local work); this is the
fallback, and it keeps the delivered system self-sufficient.

Deliberately not a general-purpose fake-data library. It generates exactly what
`seed_demo` asks for and nothing else.
"""

import random
from datetime import date, datetime, time, timedelta

FIRST_NAMES = [
    "أحمد", "محمد", "محمود", "مصطفى", "خالد", "عمر", "يوسف", "إبراهيم",
    "منى", "فاطمة", "مريم", "سارة", "نورا", "هبة", "أمل", "دعاء",
    "علي", "حسن", "حسين", "طارق", "شريف", "ياسر", "رامي", "كريم",
    "زينب", "ندى", "رانيا", "سلمى", "ملك", "جنى", "لمياء", "إيمان",
]
FAMILY_NAMES = [
    "عبد الرحمن", "السيد", "عبد الله", "حسن", "الشناوي", "المصري",
    "عبد العزيز", "فؤاد", "رمضان", "سليمان", "الحديدي", "زكي",
    "عوض", "شعبان", "الغريب", "منصور", "الديب", "قنديل",
]
CITIES = ["سوهاج", "أسيوط", "القاهرة", "الجيزة", "المنيا", "قنا", "الأقصر", "بني سويف"]
STREETS = ["شارع الجمهورية", "شارع النيل", "شارع الجيش", "شارع المحطة", "شارع 26 يوليو"]
SENTENCES = [
    "تحسن ملحوظ بعد الجلسة الأولى.",
    "لا توجد أعراض جانبية حتى الآن.",
    "يُنصح بالمتابعة بعد أسبوعين.",
    "استجابة جيدة للعلاج الموضعي.",
    "تم شرح التعليمات للمريض بالكامل.",
    "الحالة مستقرة ولا تستدعي تدخلاً إضافياً.",
    "يُفضل تجنب التعرض المباشر للشمس.",
    "أُوصي بإعادة التقييم عند الحاجة.",
]


class DemoData:
    """Enough of Faker's surface for seed_demo, and no more."""

    def __init__(self, seed=None):
        self._random = random.Random(seed)
        # Drives the `unique` variants below. A counter rather than random
        # values, so uniqueness is guaranteed instead of merely likely.
        self._counter = 0

    def name(self):
        return (
            f"{self._random.choice(FIRST_NAMES)} "
            f"{self._random.choice(FAMILY_NAMES)}"
        )

    def phone_number(self):
        # Egyptian mobile shape. Kept well inside the 32-character column, and
        # varied enough that the per-tenant uniqueness constraints are exercised.
        prefix = self._random.choice(["010", "011", "012", "015"])
        return prefix + "".join(str(self._random.randint(0, 9)) for _ in range(8))

    def address(self):
        return (
            f"{self._random.choice(STREETS)}، "
            f"{self._random.choice(CITIES)}"
        )

    def sentence(self):
        return self._random.choice(SENTENCES)

    def date_between(self, start_date="-30d", end_date="today"):
        return self._date_between(start_date, end_date)

    def date_time_between(self, start_date="-30d", end_date="now"):
        moment = self._date_between(start_date, end_date)
        return datetime.combine(
            moment,
            time(self._random.randint(9, 18), self._random.choice([0, 15, 30, 45])),
        )

    @property
    def unique(self):
        """Faker exposes guaranteed-unique variants under `.unique`, and the
        seeder relies on that for national IDs and e-mail addresses — both of
        which have uniqueness constraints, so a collision is a failed seed
        rather than a cosmetic repeat. Returning self works because the two
        methods below draw from counters, not from a random pool.
        """
        return self

    def numerify(self, text="##########"):
        """Faker replaces each # with a random digit. Here the digits come from
        a counter padded to the requested width, which makes uniqueness a
        property of the generator rather than a probability."""
        width = text.count("#")
        self._counter += 1
        value = str(self._counter).rjust(width, "0")[-width:] if width else ""
        out, digits = [], iter(value)
        for char in text:
            out.append(next(digits) if char == "#" else char)
        return "".join(out)

    def email(self):
        self._counter += 1
        return f"demo{self._counter}@example.test"

    def date_of_birth(self, minimum_age=1, maximum_age=90):
        today = date.today()
        age = self._random.randint(minimum_age, maximum_age)
        return today - timedelta(days=age * 365 + self._random.randint(0, 364))

    # ------------------------------------------------------------------ helpers

    def _date_between(self, start_date, end_date):
        today = date.today()
        start = today - timedelta(days=self._offset_days(start_date))
        end = today - timedelta(days=self._offset_days(end_date))
        if start > end:
            start, end = end, start
        span = (end - start).days
        return start + timedelta(days=self._random.randint(0, max(span, 0)))

    @staticmethod
    def _offset_days(value):
        """Understands Faker's "-30d" / "today" / "now" shorthand, which is the
        only form seed_demo uses."""
        if value in ("today", "now"):
            return 0
        text = str(value).strip().lstrip("+")
        negative = text.startswith("-")
        digits = "".join(ch for ch in text if ch.isdigit())
        days = int(digits or 0)
        return days if negative else -days


def get_generator(seed=None):
    """Faker when it is installed, the fallback otherwise.

    Faker gives richer variety for local development; the fallback is what makes
    the seeder work on a production install, where Faker is deliberately absent.
    Returns the generator and a label so the command can say which it used —
    silently switching data sources would be confusing when the output differs.
    """
    try:
        from faker import Faker
    except ImportError:
        return DemoData(seed), "built-in"

    generator = Faker("ar_EG")
    Faker.seed(seed)
    return generator, "Faker"
