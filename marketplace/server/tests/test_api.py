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
