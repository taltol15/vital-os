"""Auth, schema, signature, and rate-limit coverage for the catalog service."""

from __future__ import annotations

import base64
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat
from fastapi.testclient import TestClient

from vital_catalog import verify_catalog_signature
from vital_market.app import Settings, create_app

ROOT = Path(__file__).resolve().parents[2]


def sample_item(item_id: str = "celluloid") -> dict:
    return {
        "id": item_id,
        "name": "Celluloid",
        "summary": "A small GTK video player.",
        "description": "Plays local media.",
        "icon": {
            "url": "bundled://icons/media.svg",
            "sha256": "a" * 64,
        },
        "version": "system",
        "category": "Media",
        "publisher": "Celluloid contributors",
        "homepage": "https://celluloid-player.github.io/",
        "license": "GPL-3.0-or-later",
        "install": {"method": "apt", "package": "celluloid"},
        "min_os_version": "0.1.0",
    }


def make_client(tmp_path: Path, limit: int = 30) -> tuple[TestClient, Path]:
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    key_path = tmp_path / "market.key"
    key_path.write_bytes(pem)
    settings = Settings(
        db_path=tmp_path / "market.db",
        data_dir=tmp_path / "data",
        signing_key_file=key_path,
        rate_limit=limit,
        rate_window=60,
    )
    return TestClient(create_app(settings)), key_path


def test_admin_requires_auth(tmp_path: Path) -> None:
    client, _key = make_client(tmp_path)
    response = client.post("/v1/admin/items", json=sample_item())
    assert response.status_code == 401
    response = client.put("/v1/admin/items/celluloid", json=sample_item())
    assert response.status_code == 401
    response = client.delete("/v1/admin/items/celluloid")
    assert response.status_code == 401
    response = client.post("/v1/admin/artifacts", content=b"hello")
    assert response.status_code == 401
    catalog = client.get("/v1/catalog")
    assert catalog.status_code == 200


def test_unknown_token_is_rejected(tmp_path: Path) -> None:
    client, _key = make_client(tmp_path)
    response = client.post(
        "/v1/admin/items",
        json=sample_item(),
        headers={"Authorization": "Bearer vmt_not-a-real-token"},
    )
    assert response.status_code == 401


def test_schema_validation(tmp_path: Path) -> None:
    client, key_path = make_client(tmp_path)
    token = _insert_token(tmp_path, key_path)
    bad = sample_item()
    del bad["name"]
    bad["install"] = {"method": "script", "url": "http://insecure.example/run.sh"}
    response = client.post(
        "/v1/admin/items",
        json=bad,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422
    body = response.json()["detail"]["errors"]
    assert any("name" in message for message in body)


def test_catalog_is_signed_and_cached(tmp_path: Path) -> None:
    client, key_path = make_client(tmp_path)
    token = _insert_token(tmp_path, key_path)
    created = client.post(
        "/v1/admin/items",
        json=sample_item(),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert created.status_code == 200
    listed = client.get("/v1/catalog")
    assert listed.status_code == 200
    assert listed.headers["etag"]
    catalog = json.loads(listed.content)
    public = client.get("/v1/public-key").json()["public_key"]
    assert verify_catalog_signature(catalog, public)
    assert catalog["items"][0]["id"] == "celluloid"
    again = client.get("/v1/catalog", headers={"If-None-Match": listed.headers["etag"]})
    assert again.status_code == 304


def test_rate_limit(tmp_path: Path) -> None:
    client, key_path = make_client(tmp_path, limit=2)
    token = _insert_token(tmp_path, key_path)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.delete("/v1/admin/items/missing", headers=headers).status_code == 404
    assert client.delete("/v1/admin/items/missing", headers=headers).status_code == 404
    limited = client.delete("/v1/admin/items/missing", headers=headers)
    assert limited.status_code == 429


def test_artifact_round_trip(tmp_path: Path) -> None:
    client, key_path = make_client(tmp_path)
    token = _insert_token(tmp_path, key_path)
    uploaded = client.post(
        "/v1/admin/artifacts",
        content=b"example-bytes",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert uploaded.status_code == 200
    digest = uploaded.json()["sha256"]
    fetched = client.get(f"/v1/artifacts/{digest}")
    assert fetched.status_code == 200
    assert fetched.content == b"example-bytes"


def test_canonical_api_prefix(tmp_path: Path) -> None:
    client, key_path = make_client(tmp_path)
    token = _insert_token(tmp_path, key_path)
    created = client.post(
        "/api/v1/admin/items",
        json=sample_item(),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert created.status_code == 200
    listed = client.get("/api/v1/catalog")
    assert listed.status_code == 200
    assert json.loads(listed.content)["items"][0]["id"] == "celluloid"
    public = client.get("/api/v1/public-key")
    assert public.status_code == 200


def test_mgmt_session_csrf_and_bearer_separation(tmp_path: Path) -> None:
    client, key_path = make_client(tmp_path)
    token = _insert_token(tmp_path, key_path)
    assert client.post("/mgmt/items", data={"id": "x"}).status_code == 401
    assert client.post("/mgmt/publish", data={"csrf": "nope"}).status_code == 401
    assert client.post("/api/v1/admin/items", json=sample_item()).status_code == 401
    signed_in = client.post("/mgmt/login", data={"token": token}, follow_redirects=False)
    assert signed_in.status_code == 303
    cookie = signed_in.headers["set-cookie"]
    assert "vital_mgmt=" in cookie
    assert "HttpOnly" in cookie
    assert "Path=/mgmt" in cookie
    assert "samesite=strict" in cookie.lower()
    missing = client.post("/mgmt/publish", data={})
    assert missing.status_code == 403
    home = client.get("/mgmt")
    assert home.status_code == 200
    assert "Downloads" in home.text
    assert "Installs" in home.text
    assert "Live" in home.text
    csrf = _csrf(home.text)
    published = client.post("/mgmt/publish", data={"csrf": csrf})
    assert published.status_code == 200
    leaked = client.post("/api/v1/admin/items", json=sample_item())
    assert leaked.status_code == 401


def test_mgmt_can_create_item(tmp_path: Path) -> None:
    client, key_path = make_client(tmp_path)
    token = _insert_token(tmp_path, key_path)
    client.post("/mgmt/login", data={"token": token})
    form_page = client.get("/mgmt/items/new")
    csrf = _csrf(form_page.text)
    saved = client.post(
        "/mgmt/items",
        data={
            "csrf": csrf,
            "id": "celluloid",
            "name": "Celluloid",
            "summary": "A small GTK video player.",
            "description": "Plays local media.",
            "version": "system",
            "category": "Media",
            "publisher": "Celluloid contributors",
            "homepage": "https://celluloid-player.github.io/",
            "license": "GPL-3.0-or-later",
            "min_os_version": "0.1.0",
            "method": "apt",
            "package": "celluloid",
            "icon_url": "bundled://icons/media.svg",
            "icon_sha256": "a" * 64,
        },
        follow_redirects=False,
    )
    assert saved.status_code == 303
    catalog = json.loads(client.get("/api/v1/catalog").content)
    assert catalog["items"][0]["install"]["package"] == "celluloid"
    assert "signature" in catalog


def test_telemetry_is_anonymous_and_limited(tmp_path: Path) -> None:
    import sqlite3

    client, _key = make_client(tmp_path)
    install_id = "11111111-1111-4111-8111-111111111111"
    payload = {
        "install_id": install_id,
        "os_version": "0.1.0",
        "event": "install",
        "ts": "2026-10-05T00:00:00Z",
    }
    first = client.post("/api/v1/telemetry", json=payload)
    assert first.status_code == 204
    assert "set-cookie" not in {name.lower() for name in first.headers}
    extra = dict(payload, hostname="vital")
    assert client.post("/api/v1/telemetry", json=extra).status_code == 422
    assert client.post("/api/v1/telemetry", json={**payload, "install_id": "not-a-uuid"}).status_code == 422
    heartbeat = dict(payload, event="heartbeat", ts="2026-10-05T01:00:00Z")
    assert client.post("/api/v1/telemetry", json=heartbeat).status_code == 204
    connection = sqlite3.connect(tmp_path / "market.db")
    columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(installs)").fetchall()
    }
    assert "ip" not in columns
    assert "hostname" not in columns
    assert "ts" not in columns
    names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "requests" not in names
    row = connection.execute(
        "SELECT saw_install, os_version, last_heartbeat FROM installs"
    ).fetchone()
    assert row == (1, "0.1.0", row[2])
    assert row[2] is not None
    home_token = _insert_token(tmp_path, tmp_path / "market.key")
    client.post("/mgmt/login", data={"token": home_token})
    page = client.get("/mgmt")
    assert ">1<" in page.text or "1" in page.text
    assert "Downloads" in page.text


def test_download_counter_sets_no_cookie(tmp_path: Path) -> None:
    from vital_market.app import Settings, create_app

    key = tmp_path / "market.key"
    key.write_bytes(b"")
    settings = Settings(
        db_path=tmp_path / "market.db",
        data_dir=tmp_path / "data",
        signing_key_file=key,
        iso_url="https://vital-os.org/releases/VitalOS-0.1.0-amd64.iso",
    )
    client = TestClient(create_app(settings))
    counted = client.get("/api/v1/downloads/iso", follow_redirects=False)
    assert counted.status_code == 302
    assert counted.headers["location"].endswith("VitalOS-0.1.0-amd64.iso")
    assert "set-cookie" not in {name.lower() for name in counted.headers}
    assert counted.headers["cache-control"] == "no-store"
    client.get("/downloads/iso", follow_redirects=False)
    import sqlite3

    value = sqlite3.connect(tmp_path / "market.db").execute(
        "SELECT value FROM counters WHERE name = 'downloads'"
    ).fetchone()[0]
    assert value == 2


def _csrf(page: str) -> str:
    marker = 'name="csrf" value="'
    start = page.index(marker) + len(marker)
    return page[start : page.index('"', start)]


def _insert_token(tmp_path: Path, key_path: Path) -> str:
    import hashlib
    import sqlite3

    del key_path
    token = "vmt_test-token"
    db_path = tmp_path / "market.db"
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS tokens (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "INSERT INTO tokens (name, token_hash, created_at) VALUES (?, ?, ?)",
        ("test", hashlib.sha256(token.encode()).hexdigest(), "2026-10-05T00:00:00Z"),
    )
    connection.commit()
    connection.close()
    return token
