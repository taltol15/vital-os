"""Vital Assistant: ask for a command, confirm, then run it.

Keys live in the system keyring. Prompts go only to the provider the user
chose. Nothing in this module talks to vital-os.org.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

DEFAULT_GROK_URL = "https://api.x.ai/v1"
DEFAULT_GROK_MODEL = "grok-3"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "llama3.2"
SECRET_SCHEMA_NAME = "org.vitalos.Assistant"
SYSTEM_PROMPT = (
    "You are Vital Assistant on Vital OS, an original Ubuntu 24.04 desktop. "
    "Reply with exactly two lines and no markdown:\n"
    "COMMAND: one shell command, or NONE if no command is appropriate\n"
    "EXPLANATION: one or two short sentences\n"
    "Do not tell the user to run the command. Do not include extra lines."
)

_COMMAND_RE = re.compile(r"^COMMAND:\s*(.*)$", re.MULTILINE)
_EXPLANATION_RE = re.compile(r"^EXPLANATION:\s*(.*)$", re.MULTILINE)

# Matched against the command only. A hit means the user must type the
# command or the word yes. A plain "y" is not enough.
_RISKS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\brm\b[^|\n]*\s-[A-Za-z]*r[A-Za-z]*f", re.IGNORECASE), "rm -rf"),
    (re.compile(r"\brm\b[^|\n]*\s-[A-Za-z]*f[A-Za-z]*r", re.IGNORECASE), "rm -rf"),
    (re.compile(r"(?:^|[;&|`\n])\s*dd\b", re.IGNORECASE), "dd"),
    (re.compile(r"\bmkfs(?:\.[A-Za-z0-9]+)?\b", re.IGNORECASE), "mkfs"),
    (re.compile(r"\bchmod\b[^|\n]*-R[^|\n]*777", re.IGNORECASE), "chmod -R 777"),
    (re.compile(r"\bchown\b[^|\n]*-R[^|\n]*(?:\s|/)\/(?:\s|$)", re.IGNORECASE), "chown -R of /"),
    (re.compile(r">\s*/dev/(?:sd|nvme|vd|hd|mmcblk)"), "overwrite a disk device"),
    (re.compile(r"\b(?:wget|curl)\b[^|\n]*\|\s*(?:sudo\s+)?(?:ba)?sh\b", re.IGNORECASE), "pipe a download into a shell"),
    (re.compile(r":\(\)\s*\{"), "fork bomb"),
    (re.compile(r"\bwipefs\b", re.IGNORECASE), "wipefs"),
    (re.compile(r"\bshred\b", re.IGNORECASE), "shred"),
)


class AssistantError(Exception):
    """A user-facing failure that is not a crash."""


@dataclass
class Suggestion:
    command: str
    explanation: str
    risk: str | None

    @property
    def dangerous(self) -> bool:
        return self.risk is not None


_HOTKEY_RE = re.compile(r"^(?:<(?:Super|Shift|Control|Alt|Primary)>)+(?:space|[A-Za-z0-9])$")


@dataclass
class ModelTurn:
    text: str
    tool_calls: list[tuple[str, dict]]


@dataclass
class Settings:
    provider: str = "grok"
    model: str = ""
    base_url: str = ""
    shell_hook: bool = False
    send_context: bool = False
    hotkey: str = "<Super>space"
    language: str = "system"
    actions_enabled: bool = True
    offer_files: bool = False
    offer_window: bool = False
    offer_clipboard: bool = False
    offer_screenshot: bool = False
    history_enabled: bool = True
    local_device: str = "auto"


class MemoryKeyStore:
    """Test double. Production uses the Secret Service."""

    def __init__(self) -> None:
        self._secrets: dict[str, str] = {}

    def store(self, provider: str, secret: str) -> None:
        self._secrets[provider] = secret

    def load(self, provider: str) -> str | None:
        return self._secrets.get(provider)

    def delete(self, provider: str) -> None:
        self._secrets.pop(provider, None)


class LibsecretKeyStore:
    def __init__(self) -> None:
        import gi

        gi.require_version("Secret", "1")
        from gi.repository import Secret

        self._Secret = Secret
        self._schema = Secret.Schema.new(
            SECRET_SCHEMA_NAME,
            Secret.SchemaFlags.NONE,
            {"provider": Secret.SchemaAttributeType.STRING},
        )

    def store(self, provider: str, secret: str) -> None:
        Secret = self._Secret
        ok = Secret.password_store_sync(
            self._schema,
            {"provider": provider},
            Secret.COLLECTION_DEFAULT,
            f"Vital Assistant ({provider})",
            secret,
            None,
        )
        if not ok:
            raise AssistantError("The keyring refused to store the key.")

    def load(self, provider: str) -> str | None:
        value = self._Secret.password_lookup_sync(self._schema, {"provider": provider}, None)
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def delete(self, provider: str) -> None:
        self._Secret.password_clear_sync(self._schema, {"provider": provider}, None)


def config_paths() -> list[Path]:
    override = os.environ.get("VITAL_ASSISTANT_CONF", "").strip()
    paths = []
    if override:
        paths.append(Path(override))
    paths.append(Path.home() / ".config" / "vitalos" / "assistant.conf")
    paths.append(Path("/etc/vital/assistant.conf"))
    return paths


def load_settings(path: Path | None = None) -> Settings:
    settings = Settings()
    files = [path] if path is not None else config_paths()
    values: dict[str, str] = {}
    for candidate in reversed([item for item in files if item is not None and item.is_file()]):
        values.update(_parse_conf(candidate))
    if "provider" in values:
        settings.provider = values["provider"].strip().lower() or settings.provider
    if "model" in values:
        settings.model = values["model"].strip()
    if "base_url" in values:
        settings.base_url = values["base_url"].strip()
    settings.shell_hook = _truthy(values.get("shell_hook", "0"))
    settings.send_context = _truthy(values.get("send_context", "0"))
    settings.actions_enabled = _truthy(values.get("actions_enabled", "1"))
    settings.offer_files = _truthy(values.get("offer_files", "0"))
    settings.offer_window = _truthy(values.get("offer_window", "0"))
    settings.offer_clipboard = _truthy(values.get("offer_clipboard", "0"))
    settings.offer_screenshot = _truthy(values.get("offer_screenshot", "0"))
    settings.history_enabled = _truthy(values.get("history_enabled", "1"))
    hotkey = values.get("hotkey", settings.hotkey).strip()
    settings.hotkey = hotkey if valid_hotkey(hotkey) else "<Super>space"
    language = values.get("language", settings.language).strip().lower()
    settings.language = language if language in {"system", "en", "he"} else "system"
    device = values.get("local_device", settings.local_device).strip().lower()
    settings.local_device = device if device in {"auto", "cpu", "gpu"} else "auto"
    env_provider = os.environ.get("VITAL_ASSISTANT_PROVIDER", "").strip().lower()
    if env_provider:
        settings.provider = env_provider
    return settings


def save_user_settings(settings: Settings, path: Path | None = None) -> None:
    destination = path or (Path.home() / ".config" / "vitalos" / "assistant.conf")
    destination.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"provider={settings.provider}",
        f"model={settings.model}",
        f"base_url={settings.base_url}",
        f"shell_hook={'1' if settings.shell_hook else '0'}",
        f"send_context={'1' if settings.send_context else '0'}",
        f"hotkey={settings.hotkey}",
        f"language={settings.language}",
        f"actions_enabled={'1' if settings.actions_enabled else '0'}",
        f"offer_files={'1' if settings.offer_files else '0'}",
        f"offer_window={'1' if settings.offer_window else '0'}",
        f"offer_clipboard={'1' if settings.offer_clipboard else '0'}",
        f"offer_screenshot={'1' if settings.offer_screenshot else '0'}",
        f"history_enabled={'1' if settings.history_enabled else '0'}",
        f"local_device={settings.local_device}",
        "",
    ]
    destination.write_text("\n".join(lines), encoding="utf-8")
    destination.chmod(0o600)


def command_risk(command: str) -> str | None:
    text = command.strip()
    if not text or text.upper() == "NONE":
        return None
    for pattern, label in _RISKS:
        if pattern.search(text):
            return label
    return None


def parse_reply(text: str) -> tuple[str, str]:
    command_match = _COMMAND_RE.search(text)
    explanation_match = _EXPLANATION_RE.search(text)
    command = command_match.group(1).strip() if command_match else ""
    if command.upper() == "NONE":
        command = ""
    if explanation_match:
        explanation = explanation_match.group(1).strip()
    else:
        explanation = text.strip()
    return command, explanation


def confirmation_accepts(command: str, answer: str, dangerous: bool) -> bool:
    text = answer.strip()
    if not text:
        return False
    if dangerous:
        return text == "yes" or text == command.strip()
    return text.lower() in {"y", "yes"}


def build_user_message(question: str, context: dict[str, str] | None) -> str:
    body = question.strip()
    if not context:
        return body
    lines = [body, "", "Shell context, included because send_context is on:"]
    for key in ("cwd", "last_command", "exit_code", "stderr", "distro"):
        if context.get(key):
            lines.append(f"{key}: {context[key]}")
    return "\n".join(lines)


class MockProvider:
    name = "mock"

    def complete(self, messages: list[dict[str, str]]) -> str:
        question = messages[-1]["content"].lower() if messages else ""
        if "delete" in question and "folder" in question:
            return (
                "COMMAND: rmdir empty-folder\n"
                "EXPLANATION: rmdir removes an empty directory. It does not recurse."
            )
        if "disk" in question and "wipe" in question:
            return (
                "COMMAND: sudo mkfs.ext4 /dev/sdb\n"
                "EXPLANATION: This formats a whole disk and destroys what is on it."
            )
        return "COMMAND: ls\nEXPLANATION: Lists the names in the current directory."

    def converse(self, messages: list[dict], tools: list[dict] | None = None) -> ModelTurn:
        question = _message_text(messages[-1]).lower() if messages else ""
        if tools and "dark mode" in question:
            return ModelTurn(
                "",
                [("gnome.set", {"schema": "org.gnome.desktop.interface", "key": "color-scheme", "value": "prefer-dark"})],
            )
        if tools and "disk space" in question:
            return ModelTurn("", [("status.disk", {})])
        if tools and "install vim" in question:
            return ModelTurn("", [("apps.install", {"source": "apt", "name": "vim"})])
        return ModelTurn(self.complete(messages), [])

    def stream(self, messages: list[dict], tools: list[dict] | None = None):
        turn = self.converse(messages, tools)
        step = 24
        for index in range(0, len(turn.text), step):
            yield ("text", turn.text[index : index + step])
        for call in turn.tool_calls:
            yield ("tool", call)


class OpenAICompatibleProvider:
    def __init__(self, name: str, base_url: str, api_key: str, model: str, require_key: bool = True) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.require_key = require_key

    def complete(self, messages: list[dict]) -> str:
        if self.require_key and not self.api_key:
            raise AssistantError(f"{self.name} needs an API key in the keyring.")
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=_provider_headers(self.api_key),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise AssistantError(f"{self.name} returned HTTP {exc.code}. {detail}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise AssistantError(f"Could not reach {self.name}: {exc}") from exc
        try:
            message = body["choices"][0]["message"]
            return str(message.get("content") or "")
        except (KeyError, IndexError, TypeError) as exc:
            raise AssistantError(f"{self.name} returned an unexpected reply.") from exc

    def converse(self, messages: list[dict], tools: list[dict] | None = None) -> ModelTurn:
        text_parts: list[str] = []
        calls: list[tuple[str, dict]] = []
        for kind, piece in self.stream(messages, tools):
            if kind == "text":
                text_parts.append(str(piece))
            elif kind == "tool" and isinstance(piece, tuple):
                calls.append(piece)
        return ModelTurn("".join(text_parts), calls)

    def stream(self, messages: list[dict], tools: list[dict] | None = None):
        if self.require_key and not self.api_key:
            raise AssistantError(f"{self.name} needs an API key in the keyring.")
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=_provider_headers(self.api_key),
            method="POST",
        )
        try:
            response = urllib.request.urlopen(request, timeout=120)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise AssistantError(f"{self.name} returned HTTP {exc.code}. {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise AssistantError(f"Could not reach {self.name}: {exc}") from exc
        try:
            yield from _iter_sse(response)
        finally:
            response.close()


class OllamaProvider:
    name = "ollama"

    def __init__(self, base_url: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    def complete(self, messages: list[dict[str, str]]) -> str:
        payload = {"model": self.model, "messages": messages, "stream": False}
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "Vital-Assistant"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise AssistantError(f"Ollama returned HTTP {exc.code}.") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise AssistantError(f"Could not reach Ollama at {self.base_url}: {exc}") from exc
        message = body.get("message") if isinstance(body, dict) else None
        if not isinstance(message, dict) or "content" not in message:
            raise AssistantError("Ollama returned an unexpected reply.")
        return str(message["content"])

    def converse(self, messages: list[dict], tools: list[dict] | None = None) -> ModelTurn:
        return ModelTurn(self.complete(messages), [])

    def stream(self, messages: list[dict], tools: list[dict] | None = None):
        text = self.complete(messages)
        yield ("text", text)


def make_provider(settings: Settings, keystore: MemoryKeyStore | LibsecretKeyStore):
    name = settings.provider
    if name == "mock":
        return MockProvider()
    if name == "ollama":
        return OllamaProvider(
            settings.base_url or DEFAULT_OLLAMA_URL,
            settings.model or DEFAULT_OLLAMA_MODEL,
        )
    if name == "local":
        from vital_local import ensure_server

        try:
            url = ensure_server(settings.local_device)
        except RuntimeError as exc:
            raise AssistantError(
                "The local model is not installed. "
                "Install Vital Local Model from Vital Marketplace."
            ) from exc
        return OpenAICompatibleProvider("Local", url, "", settings.model or "qwen3", require_key=False)
    if name == "grok":
        return OpenAICompatibleProvider(
            "Grok",
            settings.base_url or DEFAULT_GROK_URL,
            keystore.load("grok") or "",
            settings.model or DEFAULT_GROK_MODEL,
        )
    if name in {"openai", "openai-compatible"}:
        base = settings.base_url or "https://api.openai.com/v1"
        return OpenAICompatibleProvider(
            "OpenAI-compatible",
            base,
            keystore.load("openai") or "",
            settings.model or "gpt-4o-mini",
        )
    raise AssistantError(f"Unknown provider {name}. Use grok, openai, ollama, local, auto, or mock.")


def suggest(
    question: str,
    settings: Settings,
    keystore: MemoryKeyStore | LibsecretKeyStore,
    context: dict[str, str] | None = None,
) -> Suggestion:
    if not question.strip():
        raise AssistantError("Ask a question first.")
    provider = make_provider(settings, keystore)
    if settings.provider in {"grok", "openai", "openai-compatible"} and not _provider_has_key(provider):
        raise AssistantError(_connect_help(settings.provider))
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_message(question, context if settings.send_context else None)},
    ]
    reply = provider.complete(messages)
    command, explanation = parse_reply(reply)
    return Suggestion(command=command, explanation=explanation, risk=command_risk(command))


def _provider_has_key(provider: object) -> bool:
    key = getattr(provider, "api_key", None)
    return bool(key)


def _connect_help(provider: str) -> str:
    if provider == "grok":
        return (
            "No Grok key is stored. Open Vital Assistant, choose Connect Grok, "
            "and paste a key from https://console.x.ai. "
            "Third-party apps cannot use a consumer Grok sign-in. "
            "The key is saved in the system keyring and is not sent to vital-os.org."
        )
    return (
        "No API key is stored for this provider. "
        "Add one in Vital Assistant. It is saved in the system keyring only."
    )


def execute(command: str) -> int:
    """Run a confirmed command. The caller must already have accepted it."""
    completed = subprocess.run(["bash", "-lc", command], check=False)
    return completed.returncode


def format_suggestion(suggestion: Suggestion) -> str:
    lines = []
    if suggestion.command:
        lines.append(suggestion.command)
    if suggestion.explanation:
        lines.append(suggestion.explanation)
    if suggestion.risk:
        lines.append(f"Warning: this looks like {suggestion.risk}.")
        lines.append("Type the command itself, or yes, to run it. Anything else cancels.")
    elif suggestion.command:
        lines.append("Run it? [y/N]")
    return "\n".join(lines)


def prompt_for(suggestion: Suggestion) -> str:
    if not suggestion.command:
        return ""
    if suggestion.risk:
        return f"Type the command or yes to run it [{suggestion.risk}]: "
    return "Run it? [y/N] "


def default_keystore() -> MemoryKeyStore | LibsecretKeyStore:
    if os.environ.get("VITAL_ASSISTANT_KEYSTORE") == "memory":
        return MemoryKeyStore()
    try:
        return LibsecretKeyStore()
    except Exception as exc:
        raise AssistantError(
            "The system keyring is not available, so the key was not stored. "
            f"({exc})"
        ) from exc


def _parse_conf(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def valid_hotkey(value: str) -> bool:
    text = value.strip()
    return bool(text) and len(text) <= 64 and bool(_HOTKEY_RE.fullmatch(text))


def _provider_headers(api_key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json", "User-Agent": "Vital-Assistant"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _message_text(message: dict) -> str:
    content = message.get("content", "")
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text", "")))
        return "\n".join(parts)
    return str(content)


def _iter_sse(response):
    tools: dict[int, dict[str, str]] = {}
    for raw in response:
        line = raw.decode("utf-8", "replace").strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        try:
            event = json.loads(data)
        except json.JSONDecodeError:
            continue
        try:
            delta = event["choices"][0].get("delta") or {}
        except (KeyError, IndexError, TypeError):
            continue
        content = delta.get("content") or ""
        if content:
            yield ("text", str(content))
        for call in delta.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            index = int(call.get("index") or 0)
            slot = tools.setdefault(index, {"name": "", "arguments": ""})
            function = call.get("function") or {}
            if function.get("name"):
                slot["name"] += str(function["name"])
            if function.get("arguments"):
                slot["arguments"] += str(function["arguments"])
    for slot in tools.values():
        if not slot["name"]:
            continue
        try:
            args = json.loads(slot["arguments"] or "{}")
        except json.JSONDecodeError:
            args = {}
        if isinstance(args, dict):
            yield ("tool", (slot["name"], args))


def read_piped() -> str:
    import select
    import sys

    if sys.stdin is None or sys.stdin.isatty():
        return ""
    try:
        ready, _, _ = select.select([sys.stdin], [], [], 0)
    except (OSError, ValueError):
        return ""
    if not ready:
        return ""
    try:
        data = sys.stdin.read(200_000)
    except OSError:
        return ""
    return data or ""


def shell_context_from_env() -> dict[str, str]:
    release = "Vital OS"
    os_release = Path("/etc/os-release")
    if os_release.is_file():
        for line in os_release.read_text(encoding="utf-8").splitlines():
            if line.startswith("PRETTY_NAME="):
                release = line.split("=", 1)[1].strip().strip('"')
                break
    return {
        "cwd": os.getcwd(),
        "last_command": os.environ.get("VITAL_ASSISTANT_LAST", ""),
        "exit_code": os.environ.get("VITAL_ASSISTANT_EXIT", ""),
        "distro": release,
    }


def main(argv: list[str] | None = None) -> int:
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    try:
        return _dispatch(args)
    except AssistantError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except BrokenPipeError:
        return 0


def _dispatch(args: list[str]) -> int:
    if not args or args[0] in {"-h", "--help"}:
        print(
            "vital ask \"question\"\n"
            "vital suggest \"natural language\"\n"
            "vital explain\n"
            "cmd | vital ask \"what does this error mean\"\n"
            "vital connect grok|openai|ollama\n"
            "vital disconnect grok|openai\n"
            "vital status\n"
            "vital history clear\n"
            "A suggested command is shown and runs only after you confirm.\n"
            "A failed-command hint is off until shell_hook=1 in assistant.conf."
        )
        return 0
    command = args[0]
    if command == "status":
        return _status()
    if command == "connect":
        return _connect(args[1:])
    if command == "disconnect":
        return _disconnect(args[1:])
    if command == "history" and len(args) > 1 and args[1] == "clear":
        from vital_core import clear_history

        clear_history()
        print("History cleared from this computer.")
        return 0
    if command == "daemon":
        from vital_daemon import serve

        serve()
        return 0
    if command == "explain":
        return _explain(args[1:])
    if command in {"ask", "suggest"}:
        return _ask(args[1:])
    if command == "--from-hook":
        return _ask(args)
    raise AssistantError("Unknown command. Try: vital ask \"how do I delete a folder\"")


def keystore_for(settings: Settings) -> MemoryKeyStore | LibsecretKeyStore:
    if settings.provider in {"mock", "ollama", "local"}:
        return MemoryKeyStore()
    return default_keystore()


def _status() -> int:
    settings = load_settings()
    print(f"provider={settings.provider}")
    print(f"shell_hook={'on' if settings.shell_hook else 'off'}")
    print(f"send_context={'on' if settings.send_context else 'off'}")
    if settings.provider in {"grok", "openai", "openai-compatible", "auto"}:
        store = keystore_for(settings)
        account = "openai" if settings.provider in {"openai", "openai-compatible"} else "grok"
        print("key=stored" if store.load(account) else "key=missing")
    print(f"hotkey={settings.hotkey}")
    print(f"language={settings.language}")
    print(f"actions={'on' if settings.actions_enabled else 'off'}")
    try:
        from vital_local import describe_local

        local = describe_local(settings.local_device)
        print("local=ready" if local["ready"] else "local=missing")
        if local["ready"]:
            print(f"local_device={local['device']}")
    except Exception:
        print("local=missing")
    return 0


def _connect(args: list[str]) -> int:
    if not args:
        raise AssistantError("Name a provider: grok, openai, or ollama.")
    provider = args[0].strip().lower()
    settings = load_settings()
    settings.provider = "openai" if provider == "openai" else provider
    if provider == "ollama":
        save_user_settings(settings)
        print("Ollama is selected. No key is stored. The default address is http://127.0.0.1:11434.")
        return 0
    if provider not in {"grok", "openai"}:
        raise AssistantError("Connect supports grok, openai, or ollama.")
    print(_connect_help(provider))
    import getpass

    secret = getpass.getpass("API key: ").strip()
    if not secret:
        raise AssistantError("No key was entered. Nothing was stored.")
    default_keystore().store(provider, secret)
    save_user_settings(settings)
    print("Stored in the system keyring. It was not written to a file.")
    return 0


def _disconnect(args: list[str]) -> int:
    provider = (args[0] if args else "grok").strip().lower()
    if provider not in {"grok", "openai"}:
        raise AssistantError("Disconnect supports grok or openai.")
    default_keystore().delete(provider)
    print(f"Removed the {provider} key from the keyring.")
    return 0


def _explain(args: list[str]) -> int:
    from vital_context import runtime_dir

    directory = runtime_dir()
    command = _read_small(directory / "last.cmd")
    exit_code = _read_small(directory / "last.exit")
    forwarded = ["--stderr-file", str(directory / "last.err")]
    if exit_code:
        forwarded.extend(["--exit", exit_code])
    if command:
        forwarded.extend(["--command", command])
    forwarded.extend(args)
    if not any(part != "--stderr-file" and not part.startswith("--") for part in args):
        forwarded.append("Explain the last failed command and its error.")
    return _ask(forwarded)


def _read_small(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:4000].strip()
    except OSError:
        return ""


def _ask(args: list[str]) -> int:
    from_hook = False
    exit_code = ""
    last_command = ""
    stderr_file = ""
    question_parts: list[str] = []
    index = 0
    while index < len(args):
        item = args[index]
        if item == "--from-hook":
            from_hook = True
        elif item == "--exit" and index + 1 < len(args):
            index += 1
            exit_code = args[index]
        elif item == "--command" and index + 1 < len(args):
            index += 1
            last_command = args[index]
        elif item == "--stderr-file" and index + 1 < len(args):
            index += 1
            stderr_file = args[index]
        else:
            question_parts.append(item)
        index += 1
    question = " ".join(question_parts).strip()
    if from_hook and not question:
        question = "The last command failed. Suggest a fix."
    piped = "" if from_hook else read_piped()
    if piped.strip():
        question = (question + "\n\nPiped output:\n" + piped[:8000]).strip()
    if not question:
        raise AssistantError("Ask a question. Example: vital ask \"how do I delete a folder\"")
    settings = load_settings()
    if from_hook and not settings.shell_hook:
        return 0
    try:
        from vital_context import Consent
        from vital_core import apply_route, route_provider

        chosen = route_provider(settings, keystore_for(settings), Consent())
        if chosen.provider != settings.provider:
            print(chosen.reason)
            settings = apply_route(settings, chosen)
    except AssistantError:
        raise
    context = None
    if settings.send_context or from_hook or stderr_file or last_command:
        context = shell_context_from_env()
        if exit_code:
            context["exit_code"] = exit_code
        if last_command:
            context["last_command"] = last_command
        if stderr_file:
            context["stderr"] = _read_small(Path(stderr_file))
        if from_hook or stderr_file or last_command:
            settings.send_context = True
    suggestion = suggest(question, settings, keystore_for(settings), context)
    print(format_suggestion(suggestion))
    if not suggestion.command or from_hook:
        return 0
    if piped.strip():
        print("Not run. Piped input is context, never a confirmation.")
        return 0
    prompt = prompt_for(suggestion)
    try:
        answer = input(prompt)
    except EOFError:
        answer = ""
    if not confirmation_accepts(suggestion.command, answer, suggestion.dangerous):
        print("Not run.")
        return 0
    print("Running.")
    return execute(suggestion.command)


def split_command(command: str) -> list[str]:
    """Visible for tests that want the argv a non-shell runner would see."""
    return shlex.split(command)
