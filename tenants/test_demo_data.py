"""The Faker fallback used to seed a production install.

`Faker` is a development dependency and is deliberately absent from a
production install, but the demo dataset is what the system ships with — so
`seed_demo` has to run there. These tests pin the contract the seeder relies on,
because the failure mode is a seed that dies halfway and leaves a
half-provisioned system.
"""

from datetime import date, datetime

from django.test import SimpleTestCase

from tenants.management.commands._demo_data import DemoData, get_generator


class DemoDataTests(SimpleTestCase):
    def setUp(self):
        self.fake = DemoData(seed=1234)

    def test_it_provides_every_method_the_seeder_calls(self):
        """Derived from grepping the seeder. The first version of this class
        missed `unique.numerify`, because a plain `fake.<name>(` search does not
        find chained attributes — and the seed then died partway through."""
        for name in ("name", "phone_number", "address", "sentence",
                     "date_between", "date_time_between", "date_of_birth",
                     "numerify", "email"):
            with self.subTest(method=name):
                self.assertTrue(callable(getattr(self.fake, name, None)))
        self.assertTrue(callable(getattr(self.fake.unique, "numerify", None)))
        self.assertTrue(callable(getattr(self.fake.unique, "email", None)))

    def test_unique_values_really_are_unique(self):
        """Both back columns with uniqueness constraints, so a collision is a
        failed seed rather than a cosmetic repeat. Guaranteed by a counter
        rather than left to probability."""
        ids = {self.fake.unique.numerify(text="##############") for _ in range(500)}
        self.assertEqual(len(ids), 500)
        emails = {self.fake.unique.email() for _ in range(500)}
        self.assertEqual(len(emails), 500)

    def test_numerify_respects_the_requested_width(self):
        value = self.fake.unique.numerify(text="##############")
        self.assertEqual(len(value), 14)
        self.assertTrue(value.isdigit())

    def test_phone_numbers_fit_the_column(self):
        """DATA-002 widened these to 32; the generator must stay inside it."""
        for _ in range(200):
            number = self.fake.phone_number()
            self.assertLessEqual(len(number), 32)
            self.assertTrue(number.isdigit())

    def test_the_faker_date_shorthand_is_understood(self):
        """seed_demo passes Faker's "-60d" / "today" forms, so the fallback has
        to read them the same way."""
        moment = self.fake.date_between(start_date="-60d", end_date="today")
        self.assertIsInstance(moment, date)
        self.assertLessEqual(moment, date.today())
        self.assertGreaterEqual((date.today() - moment).days, 0)
        self.assertLessEqual((date.today() - moment).days, 60)

    def test_date_time_between_returns_a_datetime(self):
        moment = self.fake.date_time_between(start_date="-30d", end_date="now")
        self.assertIsInstance(moment, datetime)

    def test_date_of_birth_is_in_the_past(self):
        born = self.fake.date_of_birth(minimum_age=1, maximum_age=90)
        self.assertLess(born, date.today())

    def test_names_and_text_are_arabic(self):
        """The demo data is what a client is shown first, so Latin filler would
        be conspicuous."""
        arabic = range(0x0600, 0x0700)
        self.assertTrue(any(ord(ch) in arabic for ch in self.fake.name()))
        self.assertTrue(any(ord(ch) in arabic for ch in self.fake.sentence()))
        self.assertTrue(any(ord(ch) in arabic for ch in self.fake.address()))

    def test_the_same_seed_gives_the_same_data(self):
        first = [DemoData(seed=7).name() for _ in range(5)]
        second = [DemoData(seed=7).name() for _ in range(5)]
        self.assertEqual(first, second)

    def test_the_generator_reports_which_source_it_used(self):
        """Silently switching data sources would be confusing when the output
        differs between a developer's machine and the server."""
        generator, source = get_generator(1)
        self.assertIn(source, {"Faker", "built-in"})
        self.assertTrue(callable(generator.name))
