"""Opt-in context for one request.

Nothing here is collected unless that request's consent flags say so.
Files that look like keys are refused. Screenshot pixels are not read
by the text-only local model.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

MAX_FILES = 4
MAX_FILE_BYTES = 32_768
MAX_CLIPBOARD = 8_000
MAX_FIELD = 500

_BLOCKED_NAMES = {
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    "shadow",
    "gshadow",
    "passwd",
    "authorized_keys",
}
_BLOCKED_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".kdbx")
_PRIVATE_MARKERS = (
    "-----BEGIN PRIVATE KEY-----",
    "-----BEGIN OPENSSH PRIVATE KEY-----",
    "-----BEGIN RSA PRIVATE KEY-----",
)


@dataclass
class Consent:
    files: tuple[str, ...] = ()
    window: bool = False
    clipboard: bool = False
    screenshot: bool = False
    allow_remote: bool = False

    @property
    def any(self) -> bool:
        return bool(self.files or self.window or self.clipboard or self.screenshot)

    def kinds(self) -> list[str]:
        found = []
        if self.files:
            found.append("files")
        if self.window:
            found.append("window")
        if self.clipboard:
            found.append("clipboard")
        if self.screenshot:
            found.append("screenshot")
        return found


@dataclass
class ContextBundle:
    text: str = ""
    kinds: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    sensitive: bool = False
    image_path: str = ""


def consent_from_dict(raw: dict | None) -> Consent:
    raw = raw or {}
    files = raw.get("files") or []
    if isinstance(files, str):
        files = [files]
    clean = tuple(str(item) for item in files if isinstance(item, str))
    return Consent(
        files=clean,
        window=bool(raw.get("window")),
        clipboard=bool(raw.get("clipboard")),
        screenshot=bool(raw.get("screenshot")),
        allow_remote=bool(raw.get("allow_remote")),
    )


def blocked_file(path: Path) -> str | None:
    name = path.name.lower()
    if name in _BLOCKED_NAMES or name.endswith(_BLOCKED_SUFFIXES):
        return name
    parts = {part.lower() for part in path.parts}
    if ".ssh" in parts or ".gnupg" in parts:
        return name
    return None


def read_consented_file(path: Path) -> str:
    reason = blocked_file(path)
    if reason:
        raise ValueError(f"refusing {reason}")
    data = path.read_bytes()[: MAX_FILE_BYTES + 1]
    if b"\x00" in data:
        raise ValueError("binary file")
    text = data[:MAX_FILE_BYTES].decode("utf-8", "replace")
    for marker in _PRIVATE_MARKERS:
        if marker in text:
            raise ValueError("private key material")
    return text


def assemble_context(consent: Consent, payload: dict | None, *, local_text_only: bool) -> ContextBundle:
    """Build the text block that may be sent. Payload keys are ignored without consent."""

    payload = payload or {}
    lines: list[str] = []
    notes: list[str] = []
    kinds: list[str] = []
    image_path = ""

    if consent.files:
        kinds.append("files")
        lines.append("Selected files, included because this request allowed them:")
        for raw in consent.files[:MAX_FILES]:
            path = Path(raw).expanduser()
            try:
                if not path.is_file():
                    notes.append(f"{path.name}: not a file")
                    continue
                body = read_consented_file(path)
            except (OSError, ValueError) as exc:
                notes.append(f"{path.name}: {exc}")
                continue
            lines.append(f"--- {path} ---")
            lines.append(body)
        supplied = payload.get("files")
        if isinstance(supplied, dict):
            for name, body in list(supplied.items())[:MAX_FILES]:
                if any(str(name) == str(Path(item).name) for item in consent.files):
                    continue
                lines.append(f"--- {name} ---")
                lines.append(str(body)[:MAX_FILE_BYTES])

    if consent.window:
        kinds.append("window")
        title = str(payload.get("window_title") or "")[:MAX_FIELD]
        app = str(payload.get("window_app") or "")[:MAX_FIELD]
        if title or app:
            lines.append("Active window, included because this request allowed it:")
            if app:
                lines.append(f"app: {app}")
            if title:
                lines.append(f"title: {title}")
        else:
            notes.append("window: unavailable")

    if consent.clipboard:
        kinds.append("clipboard")
        clip = str(payload.get("clipboard") or "")[:MAX_CLIPBOARD]
        if clip:
            lines.append("Clipboard, included because this request allowed it:")
            lines.append(clip)
        else:
            notes.append("clipboard: empty")

    if consent.screenshot:
        kinds.append("screenshot")
        raw_image = str(payload.get("screenshot_path") or "")
        if local_text_only:
            notes.append("screenshot: kept on this computer; the local model reads text only")
        elif raw_image and consent.allow_remote:
            image_path = raw_image
            lines.append("A screenshot was attached for a vision-capable provider.")
        elif raw_image:
            notes.append("screenshot: not sent")
        else:
            notes.append("screenshot: not captured")

    return ContextBundle(
        text="\n".join(lines).strip(),
        kinds=kinds,
        notes=notes,
        sensitive=bool(kinds),
        image_path=image_path,
    )


def disclosure(consent: Consent, provider_label: str, remote: bool) -> str:
    if not consent.any:
        return f"No personal context is included. Answering with {provider_label}."
    items = []
    if consent.files:
        items.append(f"{len(consent.files[:MAX_FILES])} selected file(s)")
    if consent.window:
        items.append("the active window title and app")
    if consent.clipboard:
        items.append("the clipboard")
    if consent.screenshot:
        items.append("a screenshot")
    destination = provider_label if remote else "this computer only"
    return "This request includes " + ", ".join(items) + f". It goes to {destination}."


def shell_block(shell: dict[str, str] | None) -> str:
    if not shell:
        return ""
    lines = ["Shell context, included because the shell hook or send_context is on:"]
    for key in ("cwd", "last_command", "exit_code", "stderr", "distro"):
        value = shell.get(key, "")
        if value:
            lines.append(f"{key}: {value[:4000]}")
    return "\n".join(lines)


def runtime_dir() -> Path:
    override = os.environ.get("VITAL_ASSISTANT_RUNTIME_DIR", "").strip()
    if override:
        path = Path(override)
    else:
        base = os.environ.get("XDG_RUNTIME_DIR", "").strip()
        path = Path(base) / "vital-assistant" if base else Path.home() / ".cache" / "vital-assistant"
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        pass
    return path
