"""English and Hebrew catalogs, including direction."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vital_i18n import STRINGS, resolve_language, translator  # noqa: E402


class I18nTests(unittest.TestCase):
    def test_every_english_string_has_hebrew(self) -> None:
        missing = set(STRINGS["en"]) - set(STRINGS["he"])
        self.assertEqual(missing, set())

    def test_hebrew_is_right_to_left(self) -> None:
        text = translator("he")
        self.assertTrue(text.rtl)
        self.assertIn("עוזר", text("app-name"))
        self.assertFalse(translator("en").rtl)
        self.assertEqual(translator("en")("app-name"), "Vital Assistant")

    def test_system_language_follows_hebrew_locale(self) -> None:
        with mock.patch.dict(os.environ, {"LANG": "he_IL.UTF-8", "LC_ALL": "", "LC_MESSAGES": ""}, clear=False):
            self.assertEqual(resolve_language("system"), "he")
        with mock.patch.dict(os.environ, {"LANG": "en_US.UTF-8", "LC_ALL": "", "LC_MESSAGES": ""}, clear=False):
            self.assertEqual(resolve_language("system"), "en")


if __name__ == "__main__":
    unittest.main()
