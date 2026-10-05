"""Checksums, bundled paths, and catalog signatures."""

from __future__ import annotations

import base64
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from vital_catalog import (  # noqa: E402
    catalog_payload,
    download_verified,
    item_checksum,
    resolve_bundled,
    sign_bytes,
    validate_catalog,
    verify_catalog_signature,
    version_is_newer,
)


def test_version_is_newer_compares_dotted_releases() -> None:
    assert version_is_newer("0.2.1", "0.2.0")
    assert not version_is_newer("0.2.0", "0.2.0")
    assert not version_is_newer("0.1.9", "0.2.0")


def test_bundled_catalog_validates() -> None:
    import json

    catalog = json.loads((ROOT / "catalog" / "catalog.json").read_text(encoding="utf-8"))
    assert validate_catalog(catalog) == []
    example = next(item for item in catalog["items"] if item["id"] == "vital-example-note")
    assert example["example"] is True
    assert example["install"]["method"] == "script"
    assert example["checksum"] == item_checksum(example)


def test_bundled_path_cannot_escape(tmp_path: Path) -> None:
    root = tmp_path / "catalog"
    root.mkdir()
    (root / "examples").mkdir()
    target = root / "examples" / "note.sh"
    target.write_text("printf ok\n", encoding="utf-8")
    assert resolve_bundled("bundled://examples/note.sh", root) == target.resolve()
    try:
        resolve_bundled("bundled://../note.sh", root)
    except ValueError:
        return
    raise AssertionError("escaped path was accepted")


def test_signature_round_trip() -> None:
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    public = base64.b64encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
    catalog = {
        "format": 1,
        "name": "Vital Marketplace",
        "issued": "2026-10-05T00:00:00Z",
        "items": [{"id": "demo"}],
    }
    catalog["signature"] = {"alg": "ed25519", "value": sign_bytes(catalog_payload(catalog), pem)}
    assert verify_catalog_signature(catalog, public)
    catalog["name"] = "Tampered"
    assert not verify_catalog_signature(catalog, public)


def test_download_rejects_bad_hash(tmp_path: Path) -> None:
    root = tmp_path / "catalog"
    (root / "examples").mkdir(parents=True)
    script = root / "examples" / "note.sh"
    script.write_text("printf ok\n", encoding="utf-8")
    try:
        download_verified("bundled://examples/note.sh", "ab" * 32, tmp_path / "out.sh", root)
    except ValueError as exc:
        assert "mismatch" in str(exc)
        return
    raise AssertionError("bad hash was accepted")
