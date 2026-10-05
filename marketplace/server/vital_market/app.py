"""Public catalog reads and authenticated admin writes."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse
import jsonschema

from vital_catalog import (
    canonical_bytes,
    catalog_payload,
    item_checksum,
    parse_public_key,
    sign_bytes,
    validate_catalog,
    validate_item,
)

SCHEMA_PATH = Path(
    os.environ.get(
        "VITAL_MARKET_SCHEMA",
        str(Path(__file__).resolve().parents[2] / "schema" / "catalog-item.schema.json"),
    )
)


@dataclass
class Settings:
    db_path: Path
    data_dir: Path
    signing_key_file: Path | None
    rate_limit: int = 30
    rate_window: float = 60.0


def settings_from_env() -> Settings:
    return Settings(
        db_path=Path(os.environ.get("VITAL_MARKET_DB", "market.db")),
        data_dir=Path(os.environ.get("VITAL_MARKET_DATA", "data")),
        signing_key_file=Path(os.environ["VITAL_MARKET_SIGNING_KEY_FILE"])
        if os.environ.get("VITAL_MARKET_SIGNING_KEY_FILE")
        else None,
        rate_limit=int(os.environ.get("VITAL_MARKET_RATE_LIMIT", "30")),
        rate_window=float(os.environ.get("VITAL_MARKET_RATE_WINDOW", "60")),
    )


class RateLimiter:
    def __init__(self, limit: int, window: float) -> None:
        self.limit = limit
        self.window = window
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        bucket = self._hits[key]
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        if len(bucket) >= self.limit:
            return False
        bucket.append(now)
        return True


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS tokens (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS items (
            id TEXT PRIMARY KEY,
            document TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    db.commit()
    return db


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def load_item_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def schema_errors(item: dict, schema: dict) -> list[str]:
    validator = jsonschema.Draft202012Validator(schema)
    found = sorted(validator.iter_errors(item), key=lambda err: list(err.path))
    messages = []
    for error in found:
        location = "/".join(str(part) for part in error.path) or "item"
        messages.append(f"{location}: {error.message}")
    messages.extend(validate_item(item))
    # validate_item repeats some schema checks. Keep unique order.
    unique: list[str] = []
    for message in messages:
        if message not in unique:
            unique.append(message)
    return unique


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or settings_from_env()
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    (cfg.data_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    schema = load_item_schema()
    limiter = RateLimiter(cfg.rate_limit, cfg.rate_window)
    app = FastAPI(title="Vital Marketplace", version="0.1.0")
    app.state.settings = cfg
    app.state.schema = schema
    app.state.limiter = limiter

    def db() -> sqlite3.Connection:
        return connect(cfg.db_path)

    def require_admin(authorization: Annotated[str | None, Header()] = None) -> str:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="authentication required")
        token = authorization.split(" ", 1)[1].strip()
        if not token:
            raise HTTPException(status_code=401, detail="authentication required")
        digest = hash_token(token)
        with db() as connection:
            row = connection.execute(
                "SELECT token_hash FROM tokens WHERE token_hash = ?",
                (digest,),
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=401, detail="authentication required")
        if not limiter.allow(digest):
            raise HTTPException(status_code=429, detail="rate limit exceeded")
        return digest

    def signing_material() -> bytes | None:
        path = cfg.signing_key_file
        if path is None or not path.is_file():
            return None
        return path.read_bytes()

    def public_b64() -> str | None:
        pem = signing_material()
        if pem is None:
            return None
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, load_pem_private_key
        import base64

        key = load_pem_private_key(pem, password=None)
        if not isinstance(key, Ed25519PrivateKey):
            return None
        raw = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        return base64.b64encode(raw).decode("ascii")

    def catalog_document() -> dict:
        with db() as connection:
            rows = connection.execute(
                "SELECT document, updated_at FROM items ORDER BY id"
            ).fetchall()
        items = []
        issued = "1970-01-01T00:00:00Z"
        for row in rows:
            item = json.loads(row["document"])
            item["checksum"] = item_checksum(item)
            items.append(item)
            if row["updated_at"] > issued:
                issued = row["updated_at"]
        document = {
            "format": 1,
            "name": "Vital Marketplace",
            "issued": issued,
            "items": items,
        }
        # An empty catalog is still signed so clients can tell the server is empty.
        if not items:
            document["items"] = []
        pem = signing_material()
        if pem is not None and items:
            document["signature"] = {
                "alg": "ed25519",
                "key_id": "vital-catalog",
                "value": sign_bytes(catalog_payload(document), pem),
            }
        return document

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/catalog")
    def get_catalog(request: Request) -> Response:
        document = catalog_document()
        errors = []
        if document["items"]:
            errors = validate_catalog(document)
        if errors:
            raise HTTPException(status_code=500, detail="; ".join(errors))
        raw = canonical_bytes(document)
        etag = '"' + hashlib.sha256(raw).hexdigest() + '"'
        headers = {
            "ETag": etag,
            "Cache-Control": "public, max-age=60",
        }
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=headers)
        return Response(content=raw, media_type="application/json", headers=headers)

    @app.get("/v1/public-key")
    def get_public_key() -> dict[str, str]:
        value = public_b64()
        if not value or parse_public_key(value) is None:
            raise HTTPException(status_code=404, detail="signing key is not configured")
        return {"alg": "ed25519", "public_key": value}

    @app.post("/v1/admin/items")
    def create_item(payload: dict, _admin: str = Depends(require_admin)) -> dict:
        return _save_item(payload, create=True)

    @app.put("/v1/admin/items/{item_id}")
    def update_item(item_id: str, payload: dict, _admin: str = Depends(require_admin)) -> dict:
        if payload.get("id") not in (None, item_id):
            raise HTTPException(status_code=422, detail="id does not match the path")
        payload["id"] = item_id
        return _save_item(payload, create=False)

    def _save_item(payload: dict, create: bool) -> dict:
        errors = schema_errors(payload, schema)
        if errors:
            raise HTTPException(status_code=422, detail={"errors": errors})
        stored = dict(payload)
        stored.pop("signature", None)
        stored["checksum"] = item_checksum(stored)
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with db() as connection:
            existing = connection.execute(
                "SELECT id FROM items WHERE id = ?",
                (stored["id"],),
            ).fetchone()
            if create and existing is not None:
                raise HTTPException(status_code=409, detail="item already exists")
            if not create and existing is None:
                raise HTTPException(status_code=404, detail="item not found")
            connection.execute(
                """
                INSERT INTO items (id, document, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET document = excluded.document, updated_at = excluded.updated_at
                """,
                (stored["id"], json.dumps(stored, ensure_ascii=False), now),
            )
            connection.commit()
        return stored

    @app.delete("/v1/admin/items/{item_id}")
    def delete_item(item_id: str, _admin: str = Depends(require_admin)) -> dict[str, str]:
        with db() as connection:
            cursor = connection.execute("DELETE FROM items WHERE id = ?", (item_id,))
            connection.commit()
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="item not found")
        return {"deleted": item_id}

    @app.post("/v1/admin/artifacts")
    async def upload_artifact(request: Request, _admin: str = Depends(require_admin)) -> dict[str, str]:
        body = await request.body()
        if not body:
            raise HTTPException(status_code=422, detail="empty upload")
        if len(body) > 512 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="upload is larger than 512 MiB")
        digest = hashlib.sha256(body).hexdigest()
        destination = cfg.data_dir / "artifacts" / digest
        destination.write_bytes(body)
        os.chmod(destination, 0o644)
        return {"sha256": digest, "url": f"/v1/artifacts/{digest}"}

    @app.get("/v1/artifacts/{digest}")
    def download_artifact(digest: str) -> FileResponse:
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise HTTPException(status_code=404, detail="not found")
        path = cfg.data_dir / "artifacts" / digest
        if not path.is_file():
            raise HTTPException(status_code=404, detail="not found")
        return FileResponse(path, filename=digest, media_type="application/octet-stream")

    return app


if os.environ.get("VITAL_MARKET_TESTING") == "1":
    app = None
else:
    app = create_app()
