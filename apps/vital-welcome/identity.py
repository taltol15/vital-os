"""Product name shown by Vital Welcome.

The primary line is Vital OS and its version. Ubuntu is only the base,
never the name of the product. On a Vital OS image this reads NAME,
PRETTY_NAME, and VERSION from os-release. On any other system it still
presents Vital OS, using the VERSION file in the source tree when present.
"""

from __future__ import annotations

from pathlib import Path

BASE_LINE = "based on Ubuntu 24.04 LTS"


def parse_os_release(text: str) -> dict[str, str]:
    data: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def read_os_release(path: Path = Path("/etc/os-release")) -> dict[str, str]:
    if not path.is_file():
        return {}
    return parse_os_release(path.read_text(encoding="utf-8"))


def _is_vital(release: dict[str, str]) -> bool:
    ident = release.get("ID", "").lower()
    name = release.get("NAME", "").lower()
    pretty = release.get("PRETTY_NAME", "").lower()
    return ident == "vitalos" or name.startswith("vital os") or pretty.startswith("vital os")


def product_identity(release: dict[str, str], fallback_version: str) -> tuple[str, str]:
    """Return (primary, secondary) lines for the welcome page."""
    version = (release.get("VERSION_ID") or release.get("VERSION") or fallback_version).strip()
    if _is_vital(release):
        pretty = release.get("PRETTY_NAME", "").strip()
        if pretty.lower().startswith("vital os"):
            primary = pretty
        else:
            name = release.get("NAME", "Vital OS").strip() or "Vital OS"
            primary = f"{name} {version}".strip()
        return primary, BASE_LINE
    return f"Vital OS {fallback_version}".strip(), BASE_LINE


def fallback_version(version_file: Path) -> str:
    if version_file.is_file():
        text = version_file.read_text(encoding="utf-8").strip()
        if text:
            return text
    return "0.1.0"
