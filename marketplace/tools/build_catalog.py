#!/usr/bin/env python3
"""Fill SHA-256 fields and write marketplace/catalog/catalog.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from vital_catalog import item_checksum, sha256_file, validate_catalog

CATALOG_DIR = ROOT / "catalog"
SOURCES = CATALOG_DIR / "sources"
OUTPUT = CATALOG_DIR / "catalog.json"


def materialize(source: dict) -> dict:
    item = dict(source)
    icon_file = item.pop("icon_file")
    icon_path = CATALOG_DIR / icon_file
    item["icon"] = {
        "url": f"bundled://{icon_file}",
        "sha256": sha256_file(icon_path),
    }
    install = dict(item["install"])
    local_file = install.pop("file", None)
    if local_file:
        path = CATALOG_DIR / local_file
        install["url"] = f"bundled://{local_file}"
        install["sha256"] = sha256_file(path)
    item["install"] = install
    item["screenshots"] = item.get("screenshots", [])
    item["checksum"] = item_checksum(item)
    return item


def build() -> dict:
    items = []
    for path in sorted(SOURCES.glob("*.json")):
        items.append(materialize(json.loads(path.read_text(encoding="utf-8"))))
    return {
        "format": 1,
        "name": "Vital Marketplace",
        "issued": "2026-10-05T00:00:00Z",
        "items": items,
    }


def main() -> int:
    catalog = build()
    errors = validate_catalog(catalog)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    rendered = json.dumps(catalog, indent=2, ensure_ascii=False) + "\n"
    check = "--check" in sys.argv
    if check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != rendered:
            print("catalog.json is stale; run marketplace/tools/build_catalog.py", file=sys.stderr)
            return 1
        print("catalog.json matches the sources")
        return 0
    OUTPUT.write_text(rendered, encoding="utf-8")
    print(f"wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
