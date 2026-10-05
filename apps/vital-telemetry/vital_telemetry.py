"""Anonymous Vital OS install counts.

The payload is only install_id, os_version, event, and ts. Network and disk
errors are swallowed by the command-line wrapper.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from urllib import error, request

CASPER_RE = re.compile(r"(^|\s)boot=casper(\s|$)")
CONF_PATH = Path("/etc/vital/telemetry.conf")
STATE_DIR = Path("/var/lib/vitalos/telemetry")
DEFAULT_ENDPOINT = "https://vital-os.org/api/v1/telemetry"


def conf_path() -> Path:
    override = os.environ.get("VITAL_TELEMETRY_CONF", "")
    return Path(override) if override else CONF_PATH


def state_dir() -> Path:
    override = os.environ.get("VITAL_TELEMETRY_STATE", "")
    return Path(override) if override else STATE_DIR


def read_conf(path: Path | None = None) -> dict[str, str]:
    source = path or conf_path()
    values = {"enabled": "true", "endpoint": DEFAULT_ENDPOINT}
    if not source.is_file():
        return values
    for raw in source.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def enabled(path: Path | None = None) -> bool:
    value = read_conf(path).get("enabled", "true").lower()
    return value in {"1", "true", "yes", "on"}


def write_enabled(on: bool, path: Path | None = None) -> None:
    source = path or conf_path()
    current = read_conf(source)
    endpoint = current.get("endpoint") or DEFAULT_ENDPOINT
    source.parent.mkdir(parents=True, exist_ok=True)
    text = (
        "# Anonymous counts for Vital OS. See PRIVACY.md in the source tree.\n"
        "# enabled=false stops install and heartbeat reports. Nothing else is collected.\n"
        f"enabled={'true' if on else 'false'}\n"
        f"endpoint={endpoint}\n"
    )
    source.write_text(text, encoding="utf-8")
    os.chmod(source, 0o644)


def cmdline() -> str:
    override = os.environ.get("VITAL_TELEMETRY_CMDLINE", "")
    path = Path(override) if override else Path("/proc/cmdline")
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def live_session(text: str | None = None) -> bool:
    return CASPER_RE.search(text if text is not None else cmdline()) is not None


def os_version() -> str:
    override = os.environ.get("VITAL_OS_VERSION", "").strip()
    if override:
        return override[:32]
    release = Path("/etc/os-release")
    version = "0"
    try:
        for raw in release.read_text(encoding="utf-8").splitlines():
            if raw.startswith("VERSION_ID="):
                version = raw.split("=", 1)[1].strip().strip('"')
                break
    except OSError:
        pass
    return version[:32] or "0"


def ensure_install_id(directory: Path | None = None) -> str:
    folder = directory or state_dir()
    folder.mkdir(parents=True, exist_ok=True)
    os.chmod(folder, 0o700)
    path = folder / "install_id"
    if path.is_file():
        current = path.read_text(encoding="utf-8").strip()
        if current:
            return current
    install_id = str(uuid.uuid4())
    path.write_text(install_id + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    return install_id


def prepare_event(event: str) -> dict[str, str] | None:
    """Return the JSON object to send, or None when this boot must stay quiet."""
    if event not in {"install", "heartbeat"}:
        return None
    if live_session() or not enabled():
        return None
    folder = state_dir()
    if event == "install" and (folder / "install_sent").is_file():
        return None
    from datetime import datetime, timezone

    return {
        "install_id": ensure_install_id(folder),
        "os_version": os_version(),
        "event": event,
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def post_event(payload: dict[str, str], endpoint: str, timeout: float = 5) -> None:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    req = request.Request(
        endpoint,
        data=raw,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "VitalOS-Telemetry/0.1",
            "Accept": "application/json",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as response:
        response.read()


def send(event: str) -> None:
    payload = prepare_event(event)
    if payload is None:
        return
    endpoint = read_conf().get("endpoint", "").strip()
    if not endpoint.startswith("https://"):
        return
    post_event(payload, endpoint)
    if event == "install":
        stamp = state_dir() / "install_sent"
        stamp.write_text("sent\n", encoding="utf-8")
        os.chmod(stamp, 0o600)


def _state_needs_root() -> bool:
    if os.geteuid() == 0:
        return False
    folder = state_dir()
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:
        return True
    return not os.access(folder, os.W_OK)


def main(argv: list[str] | None = None) -> int:
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    event = args[0] if args else "install"
    if _state_needs_root():
        if os.environ.get("VITAL_TELEMETRY_NO_PKEXEC") == "1":
            return 0
        os.execvp("pkexec", ["pkexec", sys.argv[0], *args])
    try:
        send(event)
    except (OSError, error.URLError, TimeoutError, ValueError):
        return 0
    return 0


def configure_main(argv: list[str] | None = None) -> int:
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in {"on", "off"}:
        print("usage: vital-telemetry-ctl on|off", file=sys.stderr)
        return 2
    if os.geteuid() != 0 and not os.access(conf_path(), os.W_OK):
        if os.environ.get("VITAL_TELEMETRY_NO_PKEXEC") == "1":
            return 1
        os.execvp("pkexec", ["pkexec", sys.argv[0], *args])
    write_enabled(args[0] == "on")
    print("telemetry enabled" if args[0] == "on" else "telemetry disabled")
    return 0
