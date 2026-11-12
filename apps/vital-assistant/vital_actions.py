"""Allowlisted system actions.

State-changing actions do nothing until the caller passes approved=True.
Privileged ones are a fixed argv through pkexec and the helper. There is
no shell and no way to pass an arbitrary root command. The argv that will
run is the argv shown to the user; a client cannot substitute a different one
because the daemon rebuilds the plan from the action name and arguments.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import stat
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from vital_context import runtime_dir

_PKG = re.compile(r"^[a-z0-9][a-z0-9+.-]{0,62}$")
_FLATPAK = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{1,120}$")
_DESKTOP = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*\.desktop$")
_ITEM = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{1,80}$")
_QUERY = re.compile(r"^[A-Za-z0-9 .+_-]{1,80}$")
_SCHEMA = re.compile(r"^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)+$")
_SECRET = re.compile(
    r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{6,}"
    r"|sk-[A-Za-z0-9_\-]{6,}"
    r"|xai-[A-Za-z0-9_\-]{6,}"
)

# schema, key -> constraint. Anything else is refused.
_GNOME: dict[tuple[str, str], dict] = {
    ("org.gnome.desktop.interface", "color-scheme"): {
        "enum": ["default", "prefer-dark", "prefer-light"]
    },
    ("org.gnome.desktop.interface", "gtk-theme"): {"enum": ["Adwaita", "Adwaita-dark"]},
    ("org.gnome.desktop.interface", "icon-theme"): {"enum": ["Papirus-Dark", "Papirus", "Adwaita"]},
    ("org.gnome.desktop.interface", "text-scaling-factor"): {"number": (0.7, 2.5)},
    ("org.gnome.desktop.interface", "clock-show-seconds"): {"bool": True},
    ("org.gnome.desktop.interface", "clock-show-weekday"): {"bool": True},
    ("org.gnome.desktop.interface", "show-battery-percentage"): {"bool": True},
    ("org.gnome.desktop.interface", "enable-hot-corners"): {"bool": True},
    ("org.gnome.settings-daemon.plugins.color", "night-light-enabled"): {"bool": True},
    ("org.gnome.desktop.sound", "event-sounds"): {"bool": True},
    ("org.gnome.desktop.wm.preferences", "button-layout"): {
        "enum": [
            "appmenu:close",
            ":close",
            "close,minimize,maximize:",
            "appmenu:minimize,maximize,close",
        ]
    },
    ("org.gnome.desktop.peripherals.touchpad", "tap-to-click"): {"bool": True},
    ("org.gnome.desktop.peripherals.touchpad", "natural-scroll"): {"bool": True},
    ("org.gnome.shell.extensions.dash-to-dock", "dock-position"): {
        "enum": ["BOTTOM", "LEFT", "RIGHT", "TOP"]
    },
}

_APPS = {
    "files": "org.gnome.Nautilus.desktop",
    "nautilus": "org.gnome.Nautilus.desktop",
    "console": "org.gnome.Console.desktop",
    "terminal": "org.gnome.Console.desktop",
    "firefox": "firefox.desktop",
    "text editor": "org.gnome.TextEditor.desktop",
    "gedit": "org.gnome.TextEditor.desktop",
    "settings": "org.gnome.Settings.desktop",
    "software": "org.gnome.Software.desktop",
    "marketplace": "vital-marketplace.desktop",
    "welcome": "vital-welcome.desktop",
    "assistant": "vital-assistant.desktop",
}

_ALIASES = {
    "gnome_set": "gnome.set",
    "app_open": "app.open",
    "apps_search": "apps.search",
    "apps_install": "apps.install",
    "apps_remove": "apps.remove",
    "status_disk": "status.disk",
    "status_updates": "status.updates",
    "status_battery": "status.battery",
    "status_network": "status.network",
}

_ACTION_LINE = re.compile(r"^ACTION:\s*(\{.*\})\s*$")


class ActionError(Exception):
    """A refused or invalid action. Safe to show to the user."""


@dataclass
class ActionPlan:
    name: str
    args: dict
    summary: str
    argv: list[str]
    mutating: bool
    privileged: bool
    internal: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "args": self.args,
            "summary": self.summary,
            "argv": self.argv,
            "mutating": self.mutating,
            "privileged": self.privileged,
            "internal": self.internal,
        }


@dataclass
class ActionResult:
    code: int
    output: str
    executed: bool


@dataclass
class RecordingRunner:
    calls: list[list[str]] = field(default_factory=list)
    output: str = "ok"
    code: int = 0

    def run(self, argv: list[str]) -> tuple[int, str]:
        self.calls.append(list(argv))
        return self.code, self.output


class SubprocessRunner:
    def run(self, argv: list[str]) -> tuple[int, str]:
        import subprocess

        try:
            completed = subprocess.run(
                argv,
                check=False,
                text=True,
                capture_output=True,
                timeout=45,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return 127, redact(str(exc))
        text = (completed.stdout or "") + (completed.stderr or "")
        return completed.returncode, redact(text)[:8000]


def canonical_name(name: str) -> str:
    cleaned = name.strip()
    return _ALIASES.get(cleaned, cleaned)


def helper_argv(command: str, name: str) -> list[str]:
    helper = os.environ.get("VITAL_ASSISTANT_HELPER", "/usr/libexec/vital-assistant-helper")
    return ["pkexec", helper, command, name]


def redact(text: str) -> str:
    return _SECRET.sub(lambda match: (match.group(1) or "") + "[redacted]", text)


def state_dir() -> Path:
    override = os.environ.get("VITAL_ASSISTANT_STATE_DIR", "").strip()
    if override:
        path = Path(override)
    else:
        base = os.environ.get("XDG_STATE_HOME", "").strip()
        root = Path(base) if base else Path.home() / ".local" / "state"
        path = root / "vitalos" / "assistant"
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        pass
    return path


def log_action(record: dict, path: Path | None = None) -> None:
    destination = path or (state_dir() / "actions.log")
    destination.parent.mkdir(parents=True, exist_ok=True)
    safe = {}
    for key, value in record.items():
        if key.lower() in {"api_key", "authorization", "secret", "token", "password"}:
            continue
        safe[key] = value
    safe.setdefault("ts", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    line = redact(json.dumps(safe, ensure_ascii=False, sort_keys=True))
    with destination.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    try:
        os.chmod(destination, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def confirmation_text(plan: ActionPlan) -> str:
    shown = " ".join(shlex.quote(part) for part in plan.argv) if plan.argv else plan.summary
    lines = [plan.summary, "", "This will run:", shown]
    if plan.privileged:
        lines.append("")
        lines.append("Vital OS will ask for an administrator through polkit. This is not a root shell.")
    return "\n".join(lines)


def _require_keys(args: dict, allowed: set[str]) -> None:
    extra = set(args) - allowed
    if extra:
        raise ActionError("Unexpected argument.")
    for value in args.values():
        if isinstance(value, str) and ("\n" in value or "\x00" in value):
            raise ActionError("Arguments cannot contain newlines.")


def _gnome(args: dict) -> ActionPlan:
    _require_keys(args, {"schema", "key", "value"})
    schema = str(args.get("schema", ""))
    key = str(args.get("key", ""))
    value = args.get("value")
    if not _SCHEMA.fullmatch(schema):
        raise ActionError("That setting schema is not allowlisted.")
    spec = _GNOME.get((schema, key))
    if spec is None:
        raise ActionError("That setting is not allowlisted.")
    rendered = _coerce(value, spec)
    summary = f"Set {schema} {key} to {rendered}."
    return ActionPlan(
        name="gnome.set",
        args={"schema": schema, "key": key, "value": rendered},
        summary=summary,
        argv=["gsettings", "set", schema, key, rendered],
        mutating=True,
        privileged=False,
    )


def _coerce(value: object, spec: dict) -> str:
    if "enum" in spec:
        text = str(value)
        if text not in spec["enum"]:
            raise ActionError("That value is not allowlisted.")
        return text
    if spec.get("bool"):
        if isinstance(value, bool):
            return "true" if value else "false"
        text = str(value).strip().lower()
        if text in {"true", "1", "yes", "on"}:
            return "true"
        if text in {"false", "0", "no", "off"}:
            return "false"
        raise ActionError("That value must be true or false.")
    if "number" in spec:
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ActionError("That value must be a number.") from exc
        low, high = spec["number"]
        if not low <= number <= high:
            raise ActionError("That number is outside the allowlisted range.")
        return f"{number:.2f}".rstrip("0").rstrip(".")
    raise ActionError("That setting cannot be changed.")


def _desktop_id(args: dict) -> str:
    if "desktop" in args:
        desktop = str(args["desktop"])
        if not _DESKTOP.fullmatch(desktop):
            raise ActionError("That application id is not allowed.")
        return desktop
    name = str(args.get("name", "")).strip().lower()
    desktop = _APPS.get(name)
    if desktop is None:
        raise ActionError("That application is not in the allowlist. Pass a .desktop id that you can see.")
    return desktop


def _open_app(args: dict) -> ActionPlan:
    _require_keys(args, {"desktop", "name"})
    if not args.get("desktop") and not args.get("name"):
        raise ActionError("Name an application.")
    desktop = _desktop_id(args)
    return ActionPlan(
        name="app.open",
        args={"desktop": desktop},
        summary=f"Open {desktop}.",
        argv=["gtk-launch", desktop],
        mutating=True,
        privileged=False,
    )


def _search(args: dict) -> ActionPlan:
    _require_keys(args, {"query"})
    query = str(args.get("query", "")).strip()
    if not _QUERY.fullmatch(query):
        raise ActionError("The search can use letters, numbers, spaces, and .+_- only.")
    return ActionPlan(
        name="apps.search",
        args={"query": query},
        summary=f"Search apt and the Vital Marketplace catalog for {query}.",
        argv=["apt-cache", "search", query],
        mutating=False,
        privileged=False,
    )


def _package_plan(name: str, args: dict, remove: bool) -> ActionPlan:
    _require_keys(args, {"source", "name"})
    source = str(args.get("source", "")).strip().lower()
    target = str(args.get("name", "")).strip()
    if source == "apt":
        if not _PKG.fullmatch(target) or ".." in target:
            raise ActionError("That apt package name is not allowed.")
        command = "remove-apt" if remove else "install-apt"
        verb = "Remove" if remove else "Install"
        summary = f"{verb} the apt package {target}."
    elif source == "flatpak":
        if not _FLATPAK.fullmatch(target):
            raise ActionError("That Flatpak id is not allowed.")
        command = "remove-flatpak" if remove else "install-flatpak"
        verb = "Remove" if remove else "Install"
        summary = f"{verb} the Flatpak {target}."
    elif source == "marketplace":
        if not _ITEM.fullmatch(target):
            raise ActionError("That Marketplace id is not allowed.")
        command = "remove-marketplace" if remove else "install-marketplace"
        verb = "Remove" if remove else "Install"
        summary = (
            f"{verb} Marketplace item {target}. "
            "The Marketplace helper checks the catalog checksum before it changes the system."
        )
    else:
        raise ActionError("Source must be apt, flatpak, or marketplace.")
    return ActionPlan(
        name=name,
        args={"source": source, "name": target},
        summary=summary,
        argv=helper_argv(command, target),
        mutating=True,
        privileged=True,
    )


def _status(name: str, summary: str, argv: list[str], internal: str = "") -> ActionPlan:
    return ActionPlan(
        name=name,
        args={},
        summary=summary,
        argv=argv,
        mutating=False,
        privileged=False,
        internal=internal,
    )


def plan_action(name: str, args: dict | None) -> ActionPlan:
    if not isinstance(args, dict):
        raise ActionError("Action arguments must be an object.")
    action = canonical_name(name)
    if action == "gnome.set":
        return _gnome(args)
    if action == "app.open":
        return _open_app(args)
    if action == "apps.search":
        return _search(args)
    if action == "apps.install":
        return _package_plan(action, args, remove=False)
    if action == "apps.remove":
        return _package_plan(action, args, remove=True)
    if args:
        raise ActionError("That status action takes no arguments.")
    if action == "status.disk":
        return _status("status.disk", "Show disk space for the root filesystem.", ["df", "-h", "/"])
    if action == "status.updates":
        return _status(
            "status.updates",
            "Simulate apt upgrade and list what would change. Nothing is installed.",
            ["apt-get", "-s", "upgrade"],
        )
    if action == "status.battery":
        return _status(
            "status.battery",
            "Read battery capacity from /sys/class/power_supply. No command is started.",
            [],
            internal="battery",
        )
    if action == "status.network":
        return _status(
            "status.network",
            "Show NetworkManager device status.",
            ["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"],
        )
    raise ActionError("That action is not allowlisted.")


def read_battery() -> str:
    root = Path("/sys/class/power_supply")
    if not root.is_dir():
        return "No power supply information."
    chunks = []
    for supply in sorted(root.iterdir()):
        kind = _sys_text(supply / "type")
        if kind not in {"Battery", "UPS"}:
            continue
        capacity = _sys_text(supply / "capacity") or "unknown"
        status = _sys_text(supply / "status") or "unknown"
        chunks.append(f"{supply.name}: {capacity}% ({status})")
    return "\n".join(chunks) if chunks else "No battery."


def _sys_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def search_catalog(query: str, catalog_path: Path | None = None) -> str:
    path = catalog_path or Path("/usr/share/vitalos/marketplace/catalog.json")
    if not path.is_file():
        dev = Path(__file__).resolve().parents[2] / "marketplace" / "catalog" / "catalog.json"
        path = dev if dev.is_file() else path
    if not path.is_file():
        return ""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    needle = query.lower()
    lines = []
    for item in document.get("items", []):
        if not isinstance(item, dict):
            continue
        blob = " ".join(str(item.get(key, "")) for key in ("id", "name", "summary", "description"))
        if needle in blob.lower():
            lines.append(f"marketplace {item.get('id')}: {item.get('name')}")
    return "\n".join(lines)


def execute_plan(
    plan: ActionPlan,
    approved: bool,
    runner: RecordingRunner | SubprocessRunner | None = None,
    *,
    log: bool = True,
) -> ActionResult:
    """Run a plan built by plan_action. Mutating plans require approved=True."""

    if plan.mutating and not approved:
        if log:
            log_action({"action": plan.name, "args": plan.args, "approved": False, "argv": plan.argv})
        raise ActionError("Cancelled. Nothing was changed.")
    if any(part in {"bash", "sh", "dash", "zsh", "sudo", "su"} for part in plan.argv):
        raise ActionError("Refusing to run a shell.")
    if "-lc" in plan.argv or "-c" in plan.argv:
        raise ActionError("Refusing to run a shell.")
    active = runner or SubprocessRunner()
    if plan.internal == "battery":
        output = read_battery()
        code = 0
    else:
        code, output = active.run(plan.argv)
        if plan.name == "apps.search":
            catalog = search_catalog(str(plan.args.get("query", "")))
            if catalog:
                output = catalog + ("\n" + output if output else "")
    if log:
        log_action(
            {
                "action": plan.name,
                "args": plan.args,
                "approved": bool(approved or not plan.mutating),
                "argv": plan.argv,
                "code": code,
                "output": output[:2000],
            }
        )
    return ActionResult(code=code, output=output, executed=True)


def parse_action_lines(text: str) -> tuple[str, list[tuple[str, dict]]]:
    kept: list[str] = []
    calls: list[tuple[str, dict]] = []
    for line in text.splitlines():
        match = _ACTION_LINE.match(line.strip())
        if not match:
            kept.append(line)
            continue
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            kept.append(line)
            continue
        name = payload.get("name") if isinstance(payload, dict) else None
        args = payload.get("args") if isinstance(payload, dict) else {}
        if isinstance(name, str) and isinstance(args, dict):
            calls.append((canonical_name(name), args))
        else:
            kept.append(line)
    return "\n".join(kept).strip(), calls


def tool_schema() -> list[dict]:
    def function(name: str, description: str, properties: dict, required: list[str]) -> dict:
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                    "additionalProperties": False,
                },
            },
        }

    string = {"type": "string"}
    return [
        function(
            "gnome_set",
            "Change one allowlisted GNOME setting. Does not run until the user confirms.",
            {"schema": string, "key": string, "value": string},
            ["schema", "key", "value"],
        ),
        function(
            "app_open",
            "Open a known application by desktop id or a short name such as files or firefox.",
            {"desktop": string, "name": string},
            [],
        ),
        function("apps_search", "Search apt and the Vital Marketplace catalog.", {"query": string}, ["query"]),
        function(
            "apps_install",
            "Install one apt package, Flatpak, or Marketplace item. Requires confirmation and polkit.",
            {"source": string, "name": string},
            ["source", "name"],
        ),
        function(
            "apps_remove",
            "Remove one apt package, Flatpak, or Marketplace item. Requires confirmation and polkit.",
            {"source": string, "name": string},
            ["source", "name"],
        ),
        function("status_disk", "Read disk space for /.", {}, []),
        function("status_updates", "Simulate an apt upgrade. Installs nothing.", {}, []),
        function("status_battery", "Read battery status.", {}, []),
        function("status_network", "Read network device status.", {}, []),
    ]


def runtime_socket() -> Path:
    return runtime_dir() / "ipc.sock"
