"""Per-user assistant daemon.

The session socket is the IPC every surface can speak. When a session bus
exists, the same handlers are also exported as org.vitalos.Assistant.
The daemon does not trust a client-supplied argv; approvals rebuild the plan.
"""

from __future__ import annotations

import json
import os
import socket
import threading
from pathlib import Path

from vital_actions import ActionError, runtime_socket
from vital_context import consent_from_dict
from vital_core import approve_action, clear_history, iter_answer, read_history

BUS_NAME = "org.vitalos.Assistant"
BUS_PATH = "/org/vitalos/Assistant"
MAX_LINE = 1_000_000


class DaemonUnavailable(Exception):
    pass


class AssistantService:
    def __init__(self) -> None:
        self._lock = threading.Lock()

    def ping(self) -> dict:
        return {"ok": True, "service": BUS_NAME}

    def status(self) -> dict:
        from vital_assistant import keystore_for, load_settings
        from vital_local import describe_local

        settings = load_settings()
        store = keystore_for(settings)
        account = "grok" if settings.provider in {"grok", "auto", "local", "mock", "ollama"} else "openai"
        key_state = "unused"
        if settings.provider in {"grok", "auto"}:
            key_state = "stored" if store.load("grok") else "missing"
        elif settings.provider in {"openai", "openai-compatible"}:
            key_state = "stored" if store.load("openai") else "missing"
        local = describe_local(settings.local_device)
        return {
            "provider": settings.provider,
            "shell_hook": settings.shell_hook,
            "send_context": settings.send_context,
            "key": key_state,
            "hotkey": settings.hotkey,
            "language": settings.language,
            "actions_enabled": settings.actions_enabled,
            "local": local,
            "history": len(read_history(1000)),
        }

    def settings_get(self) -> dict:
        from vital_assistant import load_settings

        settings = load_settings()
        return {field: getattr(settings, field) for field in settings.__dataclass_fields__}

    def settings_set(self, values: dict) -> dict:
        from vital_assistant import Settings, load_settings, save_user_settings, valid_hotkey

        current = load_settings()
        data = {field: getattr(current, field) for field in Settings.__dataclass_fields__}
        allowed = set(data)
        for key, value in values.items():
            if key not in allowed or key in {"api_key", "secret"}:
                continue
            data[key] = value
        updated = Settings(**data)
        if not valid_hotkey(updated.hotkey):
            raise ActionError("That shortcut is not valid.")
        if updated.language not in {"system", "en", "he"}:
            raise ActionError("Language must be system, en, or he.")
        if updated.local_device not in {"auto", "cpu", "gpu"}:
            raise ActionError("Device must be auto, cpu, or gpu.")
        save_user_settings(updated)
        return self.settings_get()

    def ask(self, params: dict):
        from vital_assistant import keystore_for, load_settings

        question = str(params.get("question") or "")
        settings = load_settings()
        if params.get("provider"):
            settings.provider = str(params["provider"])
        consent = consent_from_dict(params.get("consent"))
        payload = params.get("context") if isinstance(params.get("context"), dict) else {}
        shell = params.get("shell") if isinstance(params.get("shell"), dict) else None
        mode = str(params.get("mode") or "answer")
        with self._lock:
            yield from iter_answer(
                question,
                settings,
                keystore_for(settings),
                consent=consent,
                payload=payload,
                shell=shell,
                mode=mode,
                actions_enabled=settings.actions_enabled,
            )

    def approve(self, params: dict) -> dict:
        plan = params.get("plan") if isinstance(params.get("plan"), dict) else {}
        approved = bool(params.get("approved"))
        with self._lock:
            return approve_action(plan, approved)

    def history_clear(self) -> dict:
        clear_history()
        return {"cleared": True}

    def history_list(self) -> dict:
        return {"items": read_history(50)}


def _send(conn: socket.socket, payload: dict) -> None:
    line = json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n"
    conn.sendall(line)


def handle_client(conn: socket.socket, service: AssistantService) -> None:
    buffer = b""
    try:
        while b"\n" not in buffer:
            chunk = conn.recv(65536)
            if not chunk:
                return
            buffer += chunk
            if len(buffer) > MAX_LINE:
                _send(conn, {"event": "error", "message": "Request is too large."})
                return
        line = buffer.split(b"\n", 1)[0]
        try:
            request = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            _send(conn, {"event": "error", "message": "Request is not JSON."})
            return
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params") if isinstance(request.get("params"), dict) else {}
        try:
            if method == "ping":
                _send(conn, {"id": request_id, "event": "result", "result": service.ping()})
            elif method == "status":
                _send(conn, {"id": request_id, "event": "result", "result": service.status()})
            elif method == "settings.get":
                _send(conn, {"id": request_id, "event": "result", "result": service.settings_get()})
            elif method == "settings.set":
                _send(conn, {"id": request_id, "event": "result", "result": service.settings_set(params)})
            elif method == "history.clear":
                _send(conn, {"id": request_id, "event": "result", "result": service.history_clear()})
            elif method == "history.list":
                _send(conn, {"id": request_id, "event": "result", "result": service.history_list()})
            elif method == "approve":
                _send(conn, {"id": request_id, "event": "result", "result": service.approve(params)})
            elif method == "ask":
                for event in service.ask(params):
                    event = dict(event)
                    event["id"] = request_id
                    _send(conn, event)
            else:
                _send(conn, {"id": request_id, "event": "error", "message": "Unknown method."})
        except ActionError as exc:
            _send(conn, {"id": request_id, "event": "error", "message": str(exc)})
    except (OSError, BrokenPipeError):
        return
    finally:
        conn.close()


def serve(path: Path | None = None, ready: threading.Event | None = None) -> None:
    socket_path = path or runtime_socket()
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    if socket_path.exists():
        try:
            if ping(socket_path):
                if ready:
                    ready.set()
                return
        except DaemonUnavailable:
            pass
        socket_path.unlink()
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_path))
    os.chmod(socket_path, 0o600)
    server.listen(8)
    service = AssistantService()
    dbus_thread = threading.Thread(target=_try_dbus, args=(service,), daemon=True)
    dbus_thread.start()
    if ready:
        ready.set()
    try:
        while True:
            conn, _addr = server.accept()
            threading.Thread(target=handle_client, args=(conn, service), daemon=True).start()
    finally:
        server.close()
        from vital_local import stop_server

        stop_server()


def ping(path: Path | None = None, timeout: float = 0.4) -> dict:
    result = call("ping", {}, path=path, timeout=timeout)
    if not isinstance(result, dict):
        raise DaemonUnavailable("empty ping")
    return result


def call(method: str, params: dict | None = None, path: Path | None = None, timeout: float = 30) -> dict:
    socket_path = path or runtime_socket()
    if not socket_path.exists():
        raise DaemonUnavailable("assistant daemon is not running")
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout)
    try:
        client.connect(str(socket_path))
    except OSError as exc:
        raise DaemonUnavailable("assistant daemon is not running") from exc
    request = {"id": "1", "method": method, "params": params or {}}
    client.sendall(json.dumps(request).encode("utf-8") + b"\n")
    buffer = b""
    last = None
    try:
        while True:
            chunk = client.recv(65536)
            if not chunk:
                break
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                if not line.strip():
                    continue
                event = json.loads(line.decode("utf-8"))
                last = event
                if event.get("event") in {"result", "error", "done"}:
                    client.close()
                    if event.get("event") == "error":
                        from vital_assistant import AssistantError

                        raise AssistantError(str(event.get("message") or "daemon error"))
                    if event.get("event") == "result":
                        return event.get("result")
                    return event
    except TimeoutError as exc:
        raise DaemonUnavailable("assistant daemon timed out") from exc
    finally:
        try:
            client.close()
        except OSError:
            pass
    if last is None:
        raise DaemonUnavailable("assistant daemon closed the socket")
    return last


def call_events(method: str, params: dict | None = None, path: Path | None = None, timeout: float = 60) -> list[dict]:
    socket_path = path or runtime_socket()
    if not socket_path.exists():
        raise DaemonUnavailable("assistant daemon is not running")
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout)
    client.connect(str(socket_path))
    client.sendall(json.dumps({"id": "1", "method": method, "params": params or {}}).encode("utf-8") + b"\n")
    buffer = b""
    events: list[dict] = []
    while True:
        chunk = client.recv(65536)
        if not chunk:
            break
        buffer += chunk
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            if not line.strip():
                continue
            event = json.loads(line.decode("utf-8"))
            events.append(event)
            if event.get("event") in {"done", "error", "result"}:
                client.close()
                return events
    client.close()
    return events


def _try_dbus(service: AssistantService) -> None:
    if os.environ.get("VITAL_ASSISTANT_NO_DBUS") == "1":
        return
    if not os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
        return
    try:
        import dbus
        import dbus.service
        from gi.repository import GLib
    except Exception:
        return
    try:
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        bus = dbus.SessionBus()
    except Exception:
        return

    class Object(dbus.service.Object):
        def __init__(self) -> None:
            super().__init__(bus, BUS_PATH)

        @dbus.service.method(BUS_NAME, in_signature="", out_signature="s")
        def Status(self) -> str:
            return json.dumps(service.status())

        @dbus.service.method(BUS_NAME, in_signature="s", out_signature="s")
        def Ask(self, options_json: str) -> str:
            try:
                params = json.loads(options_json)
            except json.JSONDecodeError:
                return json.dumps({"error": "Request is not JSON."})
            events = list(service.ask(params if isinstance(params, dict) else {}))
            return json.dumps(events[-1] if events else {})

        @dbus.service.method(BUS_NAME, in_signature="s", out_signature="s")
        def Approve(self, options_json: str) -> str:
            try:
                params = json.loads(options_json)
            except json.JSONDecodeError:
                return json.dumps({"error": "Request is not JSON."})
            try:
                return json.dumps(service.approve(params if isinstance(params, dict) else {}))
            except ActionError as exc:
                return json.dumps({"error": str(exc)})

        @dbus.service.method(BUS_NAME, in_signature="", out_signature="b")
        def ClearHistory(self) -> bool:
            service.history_clear()
            return True

    try:
        name = dbus.service.BusName(BUS_NAME, bus)
        Object()
        del name
        GLib.MainLoop().run()
    except Exception:
        return
