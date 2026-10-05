"""Public catalog reads, anonymous counts, and authenticated admin writes."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sqlite3
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

import jsonschema
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response

from vital_catalog import (
    canonical_bytes,
    catalog_payload,
    item_checksum,
    parse_public_key,
    sign_bytes,
    validate_catalog,
    validate_item,
)
from vital_market.mgmt import artifact_page, dashboard, item_form, items_page, login_page, tokens_page

SCHEMA_PATH = Path(
    os.environ.get(
        "VITAL_MARKET_SCHEMA",
        str(Path(__file__).resolve().parents[2] / "schema" / "catalog-item.schema.json"),
    )
)

COOKIE = "vital_mgmt"
UUID_V4 = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
OS_VERSION = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._+-]{0,31}$")
TS_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:.Z+-]{1,24}$")
TELEMETRY_KEYS = frozenset({"install_id", "os_version", "event", "ts"})
MAX_UPLOAD = 512 * 1024 * 1024


@dataclass
class Settings:
    db_path: Path
    data_dir: Path
    signing_key_file: Path | None
    rate_limit: int = 30
    rate_window: float = 60.0
    public_base: str = "https://vital-os.org"
    iso_url: str | None = None
    live_days: int = 14
    telemetry_limit: int = 8
    telemetry_window: float = 3600.0
    telemetry_ip_limit: int = 40
    session_ttl: int = 7200


def settings_from_env() -> Settings:
    iso_url = os.environ.get("VITAL_ISO_URL", "").strip() or None
    return Settings(
        db_path=Path(os.environ.get("VITAL_MARKET_DB", "market.db")),
        data_dir=Path(os.environ.get("VITAL_MARKET_DATA", "data")),
        signing_key_file=Path(os.environ["VITAL_MARKET_SIGNING_KEY_FILE"])
        if os.environ.get("VITAL_MARKET_SIGNING_KEY_FILE")
        else None,
        rate_limit=int(os.environ.get("VITAL_MARKET_RATE_LIMIT", "30")),
        rate_window=float(os.environ.get("VITAL_MARKET_RATE_WINDOW", "60")),
        public_base=os.environ.get("VITAL_PUBLIC_BASE", "https://vital-os.org").rstrip("/"),
        iso_url=iso_url,
        live_days=int(os.environ.get("VITAL_LIVE_DAYS", "14")),
        telemetry_limit=int(os.environ.get("VITAL_TELEMETRY_LIMIT", "8")),
        telemetry_window=float(os.environ.get("VITAL_TELEMETRY_WINDOW", "3600")),
        session_ttl=int(os.environ.get("VITAL_MGMT_SESSION_TTL", "7200")),
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
        if not bucket:
            self._hits.pop(key, None)
            bucket = self._hits[key]
        if len(self._hits) > 10000:
            stale = [name for name, hits in self._hits.items() if not hits or now - hits[-1] > self.window]
            for name in stale:
                self._hits.pop(name, None)
        if len(bucket) >= self.limit:
            return False
        bucket.append(now)
        return True


class TelemetryGate:
    """In-memory limits. The IP hash and its salt are never written to SQLite."""

    def __init__(self, per_install: int, per_ip: int, window: float) -> None:
        self.per_install = RateLimiter(per_install, window)
        self.per_ip = RateLimiter(per_ip, window)
        self._day = ""
        self._salt = ""

    def _rotate(self) -> None:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if day == self._day:
            return
        self._day = day
        self._salt = secrets.token_hex(16)
        self.per_ip = RateLimiter(self.per_ip.limit, self.per_ip.window)

    def allow(self, install_id: str, peer: str) -> bool:
        self._rotate()
        ip_key = hashlib.sha256(f"{self._salt}|{peer}".encode("utf-8")).hexdigest()
        if not self.per_ip.allow(ip_key):
            return False
        if install_id and not self.per_install.allow(install_id):
            return False
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
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_hash TEXT PRIMARY KEY,
            csrf TEXT NOT NULL,
            token_id INTEGER NOT NULL,
            expires_at INTEGER NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS installs (
            install_id TEXT PRIMARY KEY,
            os_version TEXT NOT NULL,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            saw_install INTEGER NOT NULL DEFAULT 0,
            last_heartbeat TEXT
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS heartbeat_days (
            day TEXT NOT NULL,
            install_id TEXT NOT NULL,
            PRIMARY KEY (day, install_id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS counters (
            name TEXT PRIMARY KEY,
            value INTEGER NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS meta (
            name TEXT PRIMARY KEY,
            value TEXT NOT NULL
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
    unique: list[str] = []
    for message in messages:
        if message not in unique:
            unique.append(message)
    return unique


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def peer_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    parts = [part.strip() for part in forwarded.split(",") if part.strip()]
    if parts:
        return parts[-1]
    if request.client is not None:
        return request.client.host
    return "unknown"


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or settings_from_env()
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    (cfg.data_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    schema = load_item_schema()
    limiter = RateLimiter(cfg.rate_limit, cfg.rate_window)
    telemetry_gate = TelemetryGate(cfg.telemetry_limit, cfg.telemetry_ip_limit, cfg.telemetry_window)
    login_gate = RateLimiter(10, 60)
    app = FastAPI(title="Vital Marketplace", version="0.1.0")
    app.state.settings = cfg
    app.state.schema = schema
    app.state.limiter = limiter
    app.state.telemetry_gate = telemetry_gate

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
        import base64

        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, load_pem_private_key

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
            published = connection.execute(
                "SELECT value FROM meta WHERE name = 'published_at'"
            ).fetchone()
        items = []
        issued = "1970-01-01T00:00:00Z"
        for row in rows:
            item = json.loads(row["document"])
            item["checksum"] = item_checksum(item)
            items.append(item)
            if row["updated_at"] > issued:
                issued = row["updated_at"]
        if published is not None and published["value"] > issued:
            issued = published["value"]
        document = {
            "format": 1,
            "name": "Vital Marketplace",
            "issued": issued,
            "items": items,
        }
        pem = signing_material()
        if pem is not None and items:
            document["signature"] = {
                "alg": "ed25519",
                "key_id": "vital-catalog",
                "value": sign_bytes(catalog_payload(document), pem),
            }
        return document

    def store_bytes(body: bytes) -> dict[str, str]:
        if not body:
            raise HTTPException(status_code=422, detail="empty upload")
        if len(body) > MAX_UPLOAD:
            raise HTTPException(status_code=413, detail="upload is larger than 512 MiB")
        digest = hashlib.sha256(body).hexdigest()
        destination = cfg.data_dir / "artifacts" / digest
        destination.write_bytes(body)
        os.chmod(destination, 0o644)
        path = f"/api/v1/artifacts/{digest}"
        return {"sha256": digest, "url": f"{cfg.public_base}{path}", "path": path}

    def save_item(payload: dict, create: bool) -> dict:
        errors = schema_errors(payload, schema)
        if errors:
            raise HTTPException(status_code=422, detail={"errors": errors})
        stored = dict(payload)
        stored.pop("signature", None)
        stored["checksum"] = item_checksum(stored)
        now = utc_now()
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

    def session_row(request: Request) -> sqlite3.Row | None:
        raw = request.cookies.get(COOKIE, "")
        if not raw:
            return None
        digest = hash_token(raw)
        now = int(time.time())
        with db() as connection:
            row = connection.execute(
                "SELECT session_hash, csrf, token_id, expires_at FROM sessions WHERE session_hash = ?",
                (digest,),
            ).fetchone()
            if row is None or int(row["expires_at"]) <= now:
                connection.execute("DELETE FROM sessions WHERE session_hash = ?", (digest,))
                connection.commit()
                return None
        return row

    def require_session(request: Request) -> sqlite3.Row:
        row = session_row(request)
        if row is None:
            raise HTTPException(status_code=401, detail="authentication required")
        return row

    def csrf_ok(row: sqlite3.Row, sent: str) -> bool:
        if not sent:
            return False
        return secrets.compare_digest(sent, row["csrf"])

    def cookie_secure(request: Request) -> bool:
        proto = request.headers.get("x-forwarded-proto", "")
        return request.url.scheme == "https" or proto.split(",")[0].strip() == "https"

    def set_session_cookie(response: Response, raw: str, request: Request) -> None:
        response.set_cookie(
            COOKIE,
            raw,
            max_age=cfg.session_ttl,
            httponly=True,
            samesite="strict",
            secure=cookie_secure(request),
            path="/mgmt",
        )

    def html(body: str, status: int = 200) -> HTMLResponse:
        return HTMLResponse(
            body,
            status_code=status,
            headers={
                "Cache-Control": "no-store",
                "X-Frame-Options": "DENY",
                "Referrer-Policy": "no-referrer",
                "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'",
            },
        )

    def list_items() -> list[dict]:
        with db() as connection:
            rows = connection.execute("SELECT document FROM items ORDER BY id").fetchall()
        return [json.loads(row["document"]) for row in rows]

    def stats() -> dict:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=cfg.live_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        days = [
            (datetime.now(timezone.utc) - timedelta(days=offset)).strftime("%Y-%m-%d")
            for offset in range(6, -1, -1)
        ]
        with db() as connection:
            downloads_row = connection.execute(
                "SELECT value FROM counters WHERE name = 'downloads'"
            ).fetchone()
            installs = connection.execute(
                "SELECT COUNT(*) AS n FROM installs WHERE saw_install = 1"
            ).fetchone()["n"]
            live = connection.execute(
                "SELECT COUNT(*) AS n FROM installs WHERE last_heartbeat IS NOT NULL AND last_heartbeat >= ?",
                (cutoff,),
            ).fetchone()["n"]
            beats = []
            for day in days:
                beats.append(
                    connection.execute(
                        "SELECT COUNT(*) AS n FROM heartbeat_days WHERE day = ?",
                        (day,),
                    ).fetchone()["n"]
                )
        return {
            "downloads": int(downloads_row["value"]) if downloads_row else 0,
            "installs": int(installs),
            "live": int(live),
            "live_days": cfg.live_days,
            "heartbeats": beats,
            "days": days,
        }

    def bump_downloads() -> None:
        with db() as connection:
            connection.execute(
                """
                INSERT INTO counters (name, value) VALUES ('downloads', 1)
                ON CONFLICT(name) DO UPDATE SET value = value + 1
                """
            )
            connection.commit()

    def record_telemetry(payload: dict) -> None:
        now = utc_now()
        day = now[:10]
        install_id = payload["install_id"]
        version = payload["os_version"]
        event = payload["event"]
        with db() as connection:
            connection.execute(
                """
                INSERT INTO installs (install_id, os_version, first_seen, last_seen, saw_install, last_heartbeat)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(install_id) DO UPDATE SET
                    os_version = excluded.os_version,
                    last_seen = excluded.last_seen,
                    saw_install = MAX(installs.saw_install, excluded.saw_install),
                    last_heartbeat = COALESCE(excluded.last_heartbeat, installs.last_heartbeat)
                """,
                (
                    install_id,
                    version,
                    now,
                    now,
                    1 if event == "install" else 0,
                    now if event == "heartbeat" else None,
                ),
            )
            if event == "heartbeat":
                connection.execute(
                    "INSERT OR IGNORE INTO heartbeat_days (day, install_id) VALUES (?, ?)",
                    (day, install_id),
                )
            connection.commit()

    async def read_form(request: Request):
        form = await request.form()
        return form

    def form_text(form, key: str) -> str:
        value = form.get(key)
        if value is None or hasattr(value, "read"):
            return ""
        return str(value).strip()

    async def form_upload(form, key: str) -> bytes:
        value = form.get(key)
        if value is None or not hasattr(value, "read"):
            return b""
        if not getattr(value, "filename", ""):
            return b""
        data = await value.read()
        return data or b""

    def item_from_form(form, icon: dict[str, str] | None, artifact: dict[str, str] | None) -> dict:
        method = form_text(form, "method") or "apt"
        install: dict[str, str] = {"method": method}
        if method == "apt":
            install["package"] = form_text(form, "package")
        elif method == "flatpak":
            install["flatpak_id"] = form_text(form, "flatpak_id")
        else:
            install["url"] = artifact["url"] if artifact else form_text(form, "url")
            install["sha256"] = artifact["sha256"] if artifact else form_text(form, "sha256")
        icon_url = icon["url"] if icon else form_text(form, "icon_url")
        icon_sha = icon["sha256"] if icon else form_text(form, "icon_sha256")
        item: dict = {
            "id": form_text(form, "id"),
            "name": form_text(form, "name"),
            "summary": form_text(form, "summary"),
            "description": form_text(form, "description"),
            "icon": {"url": icon_url, "sha256": icon_sha},
            "version": form_text(form, "version") or "system",
            "category": form_text(form, "category"),
            "publisher": form_text(form, "publisher"),
            "homepage": form_text(form, "homepage"),
            "license": form_text(form, "license"),
            "install": install,
            "min_os_version": form_text(form, "min_os_version") or "0.1.0",
        }
        if form_text(form, "example") in {"yes", "on", "true"}:
            item["example"] = True
        return item

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/catalog")
    @app.get("/api/v1/catalog")
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
    @app.get("/api/v1/public-key")
    def get_public_key() -> dict[str, str]:
        value = public_b64()
        if not value or parse_public_key(value) is None:
            raise HTTPException(status_code=404, detail="signing key is not configured")
        return {"alg": "ed25519", "public_key": value}

    @app.post("/v1/admin/items")
    @app.post("/api/v1/admin/items")
    def create_item(payload: dict, _admin: str = Depends(require_admin)) -> dict:
        return save_item(payload, create=True)

    @app.put("/v1/admin/items/{item_id}")
    @app.put("/api/v1/admin/items/{item_id}")
    def update_item(item_id: str, payload: dict, _admin: str = Depends(require_admin)) -> dict:
        if payload.get("id") not in (None, item_id):
            raise HTTPException(status_code=422, detail="id does not match the path")
        payload["id"] = item_id
        return save_item(payload, create=False)

    @app.delete("/v1/admin/items/{item_id}")
    @app.delete("/api/v1/admin/items/{item_id}")
    def delete_item(item_id: str, _admin: str = Depends(require_admin)) -> dict[str, str]:
        with db() as connection:
            cursor = connection.execute("DELETE FROM items WHERE id = ?", (item_id,))
            connection.commit()
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="item not found")
        return {"deleted": item_id}

    @app.post("/v1/admin/artifacts")
    @app.post("/api/v1/admin/artifacts")
    async def upload_artifact(request: Request, _admin: str = Depends(require_admin)) -> dict[str, str]:
        body = await request.body()
        stored = store_bytes(body)
        return {"sha256": stored["sha256"], "url": stored["path"]}

    @app.get("/v1/artifacts/{digest}")
    @app.get("/api/v1/artifacts/{digest}")
    def download_artifact(digest: str) -> FileResponse:
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise HTTPException(status_code=404, detail="not found")
        path = cfg.data_dir / "artifacts" / digest
        if not path.is_file():
            raise HTTPException(status_code=404, detail="not found")
        return FileResponse(path, filename=digest, media_type="application/octet-stream")

    @app.delete("/v1/admin/tokens/{token_id}")
    @app.delete("/api/v1/admin/tokens/{token_id}")
    def revoke_token(token_id: int, _admin: str = Depends(require_admin)) -> dict[str, int]:
        with db() as connection:
            cursor = connection.execute("DELETE FROM tokens WHERE id = ?", (token_id,))
            connection.execute("DELETE FROM sessions WHERE token_id = ?", (token_id,))
            connection.commit()
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="token not found")
        return {"revoked": token_id}

    def download_iso(request: Request) -> Response:
        del request
        bump_downloads()
        headers = {"Cache-Control": "no-store"}
        if cfg.iso_url:
            return RedirectResponse(cfg.iso_url, status_code=302, headers=headers)
        return Response(status_code=204, headers=headers)

    app.add_api_route("/api/v1/downloads/iso", download_iso, methods=["GET"])
    app.add_api_route("/downloads/iso", download_iso, methods=["GET"])

    @app.post("/api/v1/telemetry")
    async def telemetry(request: Request) -> Response:
        peer = peer_ip(request)
        try:
            payload = await request.json()
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail="invalid json") from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=422, detail="payload must be an object")
        install_id = payload.get("install_id")
        install_key = install_id if isinstance(install_id, str) else ""
        if not telemetry_gate.allow(install_key or peer, peer):
            raise HTTPException(status_code=429, detail="rate limit exceeded")
        if set(payload) != TELEMETRY_KEYS:
            raise HTTPException(status_code=422, detail="payload must contain only install_id, os_version, event, ts")
        if not isinstance(install_id, str) or not UUID_V4.match(install_id):
            raise HTTPException(status_code=422, detail="install_id must be a uuid v4")
        if not isinstance(payload.get("os_version"), str) or not OS_VERSION.match(payload["os_version"]):
            raise HTTPException(status_code=422, detail="os_version is invalid")
        if payload.get("event") not in {"install", "heartbeat"}:
            raise HTTPException(status_code=422, detail="event must be install or heartbeat")
        if not isinstance(payload.get("ts"), str) or not TS_RE.match(payload["ts"]):
            raise HTTPException(status_code=422, detail="ts is invalid")
        record_telemetry(payload)
        return Response(status_code=204, headers={"Cache-Control": "no-store"})

    @app.get("/mgmt/login")
    def mgmt_login_form() -> HTMLResponse:
        return html(login_page())

    @app.post("/mgmt/login")
    async def mgmt_login(request: Request) -> Response:
        if not login_gate.allow(hashlib.sha256(peer_ip(request).encode()).hexdigest()):
            return html(login_page("Too many attempts. Wait a minute and try again."), status=429)
        form = await read_form(request)
        token = form_text(form, "token")
        digest = hash_token(token) if token else ""
        with db() as connection:
            row = connection.execute(
                "SELECT id FROM tokens WHERE token_hash = ?",
                (digest,),
            ).fetchone()
            if row is None:
                return html(login_page("That token was not accepted."), status=401)
            raw = secrets.token_urlsafe(32)
            csrf = secrets.token_urlsafe(24)
            connection.execute(
                "INSERT INTO sessions (session_hash, csrf, token_id, expires_at) VALUES (?, ?, ?, ?)",
                (hash_token(raw), csrf, int(row["id"]), int(time.time()) + cfg.session_ttl),
            )
            connection.commit()
        response = RedirectResponse("/mgmt", status_code=303)
        set_session_cookie(response, raw, request)
        return response

    @app.get("/mgmt")
    def mgmt_home(request: Request) -> Response:
        row = session_row(request)
        if row is None:
            return RedirectResponse("/mgmt/login", status_code=303)
        warning = ""
        if signing_material() is None:
            warning = "No signing key is loaded. Clients will reject this catalog until vital-market keygen has been run."
        return html(dashboard(stats(), row["csrf"], warning=warning))

    @app.post("/mgmt/logout")
    async def mgmt_logout(request: Request) -> Response:
        row = require_session(request)
        form = await read_form(request)
        if not csrf_ok(row, form_text(form, "csrf")):
            raise HTTPException(status_code=403, detail="csrf check failed")
        with db() as connection:
            connection.execute("DELETE FROM sessions WHERE session_hash = ?", (row["session_hash"],))
            connection.commit()
        response = RedirectResponse("/mgmt/login", status_code=303)
        response.delete_cookie(COOKIE, path="/mgmt")
        return response

    @app.get("/mgmt/items")
    def mgmt_items(request: Request) -> Response:
        row = session_row(request)
        if row is None:
            return RedirectResponse("/mgmt/login", status_code=303)
        return html(items_page(list_items(), row["csrf"]))

    @app.get("/mgmt/items/new")
    def mgmt_new_item(request: Request) -> Response:
        row = session_row(request)
        if row is None:
            return RedirectResponse("/mgmt/login", status_code=303)
        return html(item_form(row["csrf"], None))

    @app.get("/mgmt/items/{item_id}")
    def mgmt_edit_item(item_id: str, request: Request) -> Response:
        row = session_row(request)
        if row is None:
            return RedirectResponse("/mgmt/login", status_code=303)
        with db() as connection:
            found = connection.execute("SELECT document FROM items WHERE id = ?", (item_id,)).fetchone()
        if found is None:
            raise HTTPException(status_code=404, detail="item not found")
        return html(item_form(row["csrf"], json.loads(found["document"])))

    async def save_from_form(request: Request, *, create: bool, item_id: str | None = None) -> Response:
        row = require_session(request)
        form = await read_form(request)
        if not csrf_ok(row, form_text(form, "csrf")):
            raise HTTPException(status_code=403, detail="csrf check failed")
        icon_bytes = await form_upload(form, "icon_file")
        artifact_bytes = await form_upload(form, "artifact_file")
        icon = store_bytes(icon_bytes) if icon_bytes else None
        artifact = store_bytes(artifact_bytes) if artifact_bytes else None
        payload = item_from_form(form, icon, artifact)
        if item_id is not None:
            payload["id"] = item_id
        try:
            save_item(payload, create=create)
        except HTTPException as exc:
            detail = exc.detail
            if isinstance(detail, dict):
                message = "; ".join(detail.get("errors", []))
            else:
                message = str(detail)
            status = exc.status_code if exc.status_code in {422, 409, 404} else 422
            return html(item_form(row["csrf"], payload, error=message), status=status)
        return RedirectResponse("/mgmt/items", status_code=303)

    @app.post("/mgmt/items")
    async def mgmt_create_item(request: Request) -> Response:
        return await save_from_form(request, create=True)

    @app.post("/mgmt/items/{item_id}")
    async def mgmt_update_item(item_id: str, request: Request) -> Response:
        return await save_from_form(request, create=False, item_id=item_id)

    @app.post("/mgmt/items/{item_id}/delete")
    async def mgmt_delete_item(item_id: str, request: Request) -> Response:
        row = require_session(request)
        form = await read_form(request)
        if not csrf_ok(row, form_text(form, "csrf")):
            raise HTTPException(status_code=403, detail="csrf check failed")
        if form_text(form, "confirm") != "yes":
            raise HTTPException(status_code=422, detail="confirm the delete")
        with db() as connection:
            cursor = connection.execute("DELETE FROM items WHERE id = ?", (item_id,))
            connection.commit()
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="item not found")
        return RedirectResponse("/mgmt/items", status_code=303)

    @app.post("/mgmt/artifacts")
    async def mgmt_upload(request: Request) -> Response:
        row = require_session(request)
        form = await read_form(request)
        if not csrf_ok(row, form_text(form, "csrf")):
            raise HTTPException(status_code=403, detail="csrf check failed")
        body = await form_upload(form, "file")
        stored = store_bytes(body)
        return html(artifact_page(row["csrf"], stored["sha256"], stored["url"]))

    @app.post("/mgmt/publish")
    async def mgmt_publish(request: Request) -> Response:
        row = require_session(request)
        form = await read_form(request)
        if not csrf_ok(row, form_text(form, "csrf")):
            raise HTTPException(status_code=403, detail="csrf check failed")
        with db() as connection:
            connection.execute(
                """
                INSERT INTO meta (name, value) VALUES ('published_at', ?)
                ON CONFLICT(name) DO UPDATE SET value = excluded.value
                """,
                (utc_now(),),
            )
            connection.commit()
        return RedirectResponse("/mgmt", status_code=303)

    @app.get("/mgmt/tokens")
    def mgmt_tokens(request: Request) -> Response:
        row = session_row(request)
        if row is None:
            return RedirectResponse("/mgmt/login", status_code=303)
        with db() as connection:
            found = connection.execute(
                "SELECT id, name, created_at FROM tokens ORDER BY id"
            ).fetchall()
        listed = [(int(item["id"]), str(item["name"]), str(item["created_at"])) for item in found]
        return html(tokens_page(listed, row["csrf"]))

    @app.post("/mgmt/tokens/{token_id}/revoke")
    async def mgmt_revoke(token_id: int, request: Request) -> Response:
        row = require_session(request)
        form = await read_form(request)
        if not csrf_ok(row, form_text(form, "csrf")):
            raise HTTPException(status_code=403, detail="csrf check failed")
        with db() as connection:
            cursor = connection.execute("DELETE FROM tokens WHERE id = ?", (token_id,))
            connection.execute("DELETE FROM sessions WHERE token_id = ?", (token_id,))
            connection.commit()
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="token not found")
        if int(row["token_id"]) == token_id:
            response = RedirectResponse("/mgmt/login", status_code=303)
            response.delete_cookie(COOKIE, path="/mgmt")
            return response
        return RedirectResponse("/mgmt/tokens", status_code=303)

    return app


if os.environ.get("VITAL_MARKET_TESTING") == "1":
    app = None
else:
    app = create_app()
