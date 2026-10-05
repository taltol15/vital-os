"""Shared catalog checks for the Vital Marketplace client and server.

Downloaded artifacts are accepted only after a SHA-256 match. Remote
catalogs are accepted only with a valid ed25519 signature. The bundled
catalog is a local file shipped in the image and is the offline fallback.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
ITEM_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{1,80}$")
APT_RE = re.compile(r"^[a-z0-9][a-z0-9+.-]{0,80}$")
FLATPAK_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*(\.[A-Za-z_][A-Za-z0-9_-]*)+$")
METHODS = {"apt", "flatpak", "deb", "script"}


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def without_keys(value: dict, keys: set[str]) -> dict:
    return {key: item for key, item in value.items() if key not in keys}


def item_checksum(item: dict) -> str:
    return sha256_bytes(canonical_bytes(without_keys(item, {"checksum", "signature"})))


def parse_public_key(text: str) -> str | None:
    """Return raw ed25519 public key material as standard base64, or None."""
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)
    if not lines:
        return None
    token = "".join(lines)
    try:
        import base64

        raw = base64.b64decode(token, validate=True)
    except Exception:
        return None
    if len(raw) != 32:
        return None
    return token


def sign_bytes(payload: bytes, private_pem: bytes) -> str:
    import base64

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    key = load_pem_private_key(private_pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("signing key must be ed25519")
    return base64.b64encode(key.sign(payload)).decode("ascii")


def verify_bytes(payload: bytes, signature_b64: str, public_b64: str) -> bool:
    import base64

    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        public = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_b64, validate=True))
        public.verify(base64.b64decode(signature_b64, validate=True), payload)
    except (InvalidSignature, ValueError, TypeError):
        return False
    return True


def catalog_payload(catalog: dict) -> bytes:
    return canonical_bytes(without_keys(catalog, {"signature"}))


def verify_catalog_signature(catalog: dict, public_b64: str) -> bool:
    signature = catalog.get("signature")
    if not isinstance(signature, dict):
        return False
    if signature.get("alg") != "ed25519":
        return False
    value = signature.get("value")
    if not isinstance(value, str) or not value:
        return False
    return verify_bytes(catalog_payload(catalog), value, public_b64)


def validate_item(item: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(item, dict):
        return ["item must be an object"]
    item_id = item.get("id")
    if not isinstance(item_id, str) or not ITEM_ID_RE.match(item_id):
        errors.append("id must match ^[A-Za-z0-9][A-Za-z0-9._+-]{1,80}$")
    for key in ("name", "summary", "description", "version", "category", "publisher", "homepage", "license", "min_os_version"):
        value = item.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{key} is required")
    if isinstance(item.get("summary"), str) and len(item["summary"]) > 160:
        errors.append("summary is longer than 160 characters")
    icon = item.get("icon")
    if not isinstance(icon, dict):
        errors.append("icon is required")
    else:
        if not isinstance(icon.get("url"), str) or not icon["url"]:
            errors.append("icon.url is required")
        if not isinstance(icon.get("sha256"), str) or not SHA256_RE.match(icon["sha256"]):
            errors.append("icon.sha256 must be 64 lowercase hex characters")
    install = item.get("install")
    if not isinstance(install, dict):
        errors.append("install is required")
    else:
        method = install.get("method")
        if method not in METHODS:
            errors.append("install.method must be apt, flatpak, deb, or script")
        elif method == "apt":
            package = install.get("package", "")
            if not isinstance(package, str) or not APT_RE.match(package):
                errors.append("apt package name is invalid")
        elif method == "flatpak":
            flatpak_id = install.get("flatpak_id", "")
            if not isinstance(flatpak_id, str) or not FLATPAK_RE.match(flatpak_id):
                errors.append("flatpak_id is invalid")
        elif method in {"deb", "script"}:
            url = install.get("url", "")
            digest = install.get("sha256", "")
            if not isinstance(url, str) or not (url.startswith("https://") or url.startswith("bundled://")):
                errors.append(f"{method} url must be https or bundled")
            if not isinstance(digest, str) or not SHA256_RE.match(digest):
                errors.append(f"{method} sha256 must be 64 lowercase hex characters")
    shots = item.get("screenshots", [])
    if shots is None:
        shots = []
    if not isinstance(shots, list):
        errors.append("screenshots must be a list")
    else:
        for index, shot in enumerate(shots):
            if not isinstance(shot, dict):
                errors.append(f"screenshots[{index}] must be an object")
                continue
            if not isinstance(shot.get("url"), str) or not shot["url"]:
                errors.append(f"screenshots[{index}].url is required")
            if not isinstance(shot.get("sha256"), str) or not SHA256_RE.match(shot["sha256"]):
                errors.append(f"screenshots[{index}].sha256 is invalid")
    if "example" in item and not isinstance(item["example"], bool):
        errors.append("example must be a boolean")
    if "checksum" in item and (not isinstance(item["checksum"], str) or not SHA256_RE.match(item["checksum"])):
        errors.append("checksum must be a sha256")
    return errors


def validate_catalog(catalog: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(catalog, dict):
        return ["catalog must be an object"]
    if catalog.get("format") != 1:
        errors.append("format must be 1")
    if not isinstance(catalog.get("name"), str) or not catalog["name"].strip():
        errors.append("name is required")
    items = catalog.get("items")
    if not isinstance(items, list) or not items:
        errors.append("items must be a non-empty list")
        return errors
    seen: set[str] = set()
    for item in items:
        item_errors = validate_item(item)
        errors.extend(item_errors)
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            if item["id"] in seen:
                errors.append(f"duplicate id {item['id']}")
            seen.add(item["id"])
            if "checksum" in item and not item_errors and item.get("checksum") != item_checksum(item):
                errors.append(f"checksum mismatch for {item['id']}")
    signature = catalog.get("signature")
    if signature is not None:
        if not isinstance(signature, dict) or signature.get("alg") != "ed25519":
            errors.append("signature.alg must be ed25519")
        elif not isinstance(signature.get("value"), str) or not signature["value"]:
            errors.append("signature.value is required")
    return errors


def resolve_bundled(url: str, root: Path) -> Path:
    if not url.startswith("bundled://"):
        raise ValueError("not a bundled url")
    relative = url.removeprefix("bundled://")
    if not relative or relative.startswith("/") or "\\" in relative:
        raise ValueError("bundled path escapes the catalog")
    parts = Path(relative).parts
    if ".." in parts:
        raise ValueError("bundled path escapes the catalog")
    root_resolved = root.resolve()
    path = (root_resolved / relative).resolve()
    if path != root_resolved and root_resolved not in path.parents:
        raise ValueError("bundled path escapes the catalog")
    return path


def hashes_match(path: Path, expected: str) -> bool:
    if not SHA256_RE.match(expected):
        return False
    if not path.is_file():
        return False
    return sha256_file(path) == expected


def read_config(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def fetch_url(url: str, timeout: float = 20) -> bytes:
    if not url.startswith("https://"):
        raise ValueError("downloads must use https")
    request = urllib.request.Request(url, headers={"User-Agent": "VitalMarketplace/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.URLError as exc:
        raise ConnectionError(str(exc)) from exc


def fetch_remote_catalog(url: str, public_b64: str, timeout: float = 20) -> tuple[dict, str]:
    if not public_b64:
        raise ValueError("remote catalogs require a public key")
    raw = fetch_url(url, timeout=timeout)
    catalog = json.loads(raw.decode("utf-8"))
    errors = validate_catalog(catalog)
    if errors:
        raise ValueError("; ".join(errors))
    if not verify_catalog_signature(catalog, public_b64):
        raise ValueError("catalog signature did not verify")
    etag = sha256_bytes(raw)
    return catalog, etag


def load_client_catalog(config: dict[str, str]) -> tuple[dict, str]:
    """Return (catalog, source). source is 'remote' or 'bundled'."""
    bundled_path = Path(config.get("bundled_catalog") or "/usr/share/vitalos/marketplace/catalog.json")
    public_path = Path(config.get("public_key") or "/etc/vital/marketplace.pub")
    url = config.get("catalog_url", "").strip()
    public = ""
    if public_path.is_file():
        public = parse_public_key(public_path.read_text(encoding="utf-8")) or ""
    if url:
        try:
            catalog, _etag = fetch_remote_catalog(url, public)
            return catalog, "remote"
        except (OSError, ValueError, json.JSONDecodeError, ConnectionError):
            pass
    if not bundled_path.is_file():
        raise FileNotFoundError(f"bundled catalog missing: {bundled_path}")
    catalog = load_json(bundled_path)
    errors = validate_catalog(catalog)
    if errors:
        raise ValueError("; ".join(errors))
    return catalog, "bundled"


def catalog_root_from_config(config: dict[str, str]) -> Path:
    bundled = Path(config.get("bundled_catalog") or "/usr/share/vitalos/marketplace/catalog.json")
    return bundled.parent


def download_verified(url: str, expected: str, destination: Path, bundled_root: Path) -> None:
    if url.startswith("bundled://"):
        source = resolve_bundled(url, bundled_root)
        data = source.read_bytes()
    else:
        data = fetch_url(url)
    digest = sha256_bytes(data)
    if digest != expected:
        raise ValueError(f"sha256 mismatch: expected {expected}, got {digest}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    os.chmod(destination, 0o644)
