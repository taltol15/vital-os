"""Identity text must name Vital OS, including when os-release is Ubuntu."""

from __future__ import annotations

import unittest
from pathlib import Path

from identity import parse_os_release, product_identity

ROOT = Path(__file__).resolve().parents[2]


class IdentityTests(unittest.TestCase):
    def test_ubuntu_host_is_not_the_product_name(self) -> None:
        release = parse_os_release(
            'PRETTY_NAME="Ubuntu 24.04.4 LTS"\nNAME="Ubuntu"\nVERSION_ID="24.04"\nID=ubuntu\n'
        )
        primary, secondary = product_identity(release, "0.1.0")
        self.assertEqual(primary, "Vital OS 0.1.0")
        self.assertEqual(secondary, "based on Ubuntu 24.04 LTS")
        self.assertNotIn("Ubuntu 24.04.4", primary)

    def test_vital_os_release_uses_pretty_name(self) -> None:
        text = (ROOT / "config" / "os-release.in").read_text(encoding="utf-8")
        release = parse_os_release(text.replace("@VERSION@", "0.1.0"))
        primary, secondary = product_identity(release, "9.9.9")
        self.assertEqual(primary, "Vital OS 0.1.0")
        self.assertEqual(secondary, "based on Ubuntu 24.04 LTS")

    def test_vital_name_without_pretty(self) -> None:
        primary, _secondary = product_identity(
            {"ID": "vitalos", "NAME": "Vital OS", "VERSION_ID": "0.1.0"},
            "0.0.0",
        )
        self.assertEqual(primary, "Vital OS 0.1.0")


if __name__ == "__main__":
    unittest.main()
