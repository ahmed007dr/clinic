"""Every word the new screens show exists in both languages.

The screens keep no copy of any list: choices arrive as codes from
`/api/meta/choices/` and are shown through `choices.<group>.<code>`. So a code
added to a model with no word for it would render as a raw key — this test
fails first. It also fails on any `t('literal.key')` in the frontend source
missing from either dictionary, and on the two dictionaries drifting apart.
"""

import json
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from api.views.meta import choice_codes

FRONTEND = Path(settings.BASE_DIR) / "frontend" / "src"
I18N = FRONTEND / "i18n"
LITERAL_KEY = re.compile(r"""\bt\(\s*['"]([a-z_]+(?:\.[a-z0-9_]+)+)['"]""")

# Keys composed at runtime (`intake.steps.${step}`), listed with every value
# the code composes them from.
DYNAMIC = {
    "intake.steps": ["personal", "visit", "history", "referral", "doctor", "review"],
    "intake.doctor_mode": ["doctor", "specialty", "unknown"],
    "intake.contact": ["phone", "whatsapp", "sms", "email"],
}


def load(lang):
    return json.loads((I18N / f"{lang}.json").read_text(encoding="utf-8"))


class TranslationTests(SimpleTestCase):
    def setUp(self):
        self.ar, self.en = load("ar"), load("en")

    def test_both_languages_have_the_same_keys(self):
        self.assertEqual(sorted(set(self.ar) - set(self.en)), [])
        self.assertEqual(sorted(set(self.en) - set(self.ar)), [])

    def test_no_translation_is_blank(self):
        for lang, words in (("ar", self.ar), ("en", self.en)):
            blank = [key for key, text in words.items() if not str(text).strip()]
            self.assertEqual(blank, [], lang)

    def test_every_server_choice_has_a_word_in_both_languages(self):
        for group, codes in choice_codes().items():
            for code in codes:
                key = f"choices.{group}.{code}"
                self.assertIn(key, self.ar, key)
                self.assertIn(key, self.en, key)

    def test_every_literal_key_used_in_the_screens_exists(self):
        used = set()
        for path in FRONTEND.rglob("*.jsx"):
            used |= set(LITERAL_KEY.findall(path.read_text(encoding="utf-8")))
        self.assertTrue(used, "no t('…') calls found — the scan is broken")
        missing = sorted(key for key in used if key not in self.ar or key not in self.en)
        self.assertEqual(missing, [])

    def test_every_composed_key_exists(self):
        for prefix, values in DYNAMIC.items():
            for value in values:
                key = f"{prefix}.{value}" if prefix != "intake.contact" else f"{prefix}_{value}"
                self.assertIn(key, self.ar, key)
                self.assertIn(key, self.en, key)
