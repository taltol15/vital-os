"""One assistant core for the terminal, the overlay, and the daemon.

Provider choice, history, consent, and action confirmation all go through
this module. Surfaces do not keep a second copy of those rules.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from vital_actions import (
    ActionError,
    ActionPlan,
    RecordingRunner,
    SubprocessRunner,
    execute_plan,
    log_action,
    parse_action_lines,
    plan_action,
    redact,
    state_dir,
    tool_schema,
)
from vital_context import (
    Consent,
    assemble_context,
    consent_from_dict,
    disclosure,
    shell_block,
)

ANSWER_PROMPT = (
    "You are Vital Assistant on Vital OS, an original Ubuntu 24.04 desktop. "
    "/no_think\n"
    "Answer in the user's language, in plain prose. "
    "When a system action would help, call an allowlisted tool or emit one line:\n"
    "ACTION: {\"name\":\"status.disk\",\"args\":{}}\n"
    "Never claim an action already ran. Never invent a root shell. "
    "Do not repeat API keys. If a shell command is the right suggestion, emit\n"
    "COMMAND: one command\n"
    "EXPLANATION: one sentence\n"
    "and do not tell the user it was already run."
)

EXPLAIN_PROMPT = (
    "You are Vital Assistant. The user wants the last failed command explained. "
    "/no_think\n"
    "Reply with a short explanation of the error. "
    "If one safer command would fix it, also include:\n"
    "COMMAND: one command\n"
    "EXPLANATION: one sentence\n"
    "Do not say the command was run."
)


@dataclass
class Route:
    provider: str
    label: str
    reason: str
    remote: bool


@dataclass
class PendingAction:
    plan: ActionPlan
    summary: str


def provider_label(name: str) -> str:
    return {
        "grok": "Grok (xAI)",
        "openai": "OpenAI-compatible",
        "openai-compatible": "OpenAI-compatible",
        "ollama": "Ollama on this computer",
        "local": "On this computer (Qwen3 0.6B)",
        "mock": "Mock",
        "auto": "Automatic",
    }.get(name, name)


def route_provider(settings, keystore, consent: Consent, *, online: bool | None = None) -> Route:
    """Pick the provider for this request. Sensitive context prefers local."""

    from vital_local import local_ready

    requested = settings.provider
    ready = local_ready(getattr(settings, "local_device", "auto"))
    sensitive = consent.any

    def local(reason: str) -> Route | None:
        if not ready:
            return None
        return Route("local", provider_label("local"), reason, remote=False)

    if requested == "mock":
        return Route("mock", provider_label("mock"), "Mock provider.", remote=False)
    if requested == "ollama":
        return Route("ollama", provider_label("ollama"), "Ollama on this computer.", remote=False)
    if requested == "local":
        chosen = local("You selected the local model.")
        if chosen is None:
            raise _missing_local()
        return chosen

    if sensitive and not consent.allow_remote:
        chosen = local("Sensitive context stays on this computer.")
        if chosen is not None:
            return chosen
        if requested == "ollama":
            return Route("ollama", provider_label("ollama"), "Sensitive context uses Ollama.", remote=False)
        from vital_assistant import AssistantError

        raise AssistantError(
            "This request includes personal context. Install the local model from Vital Marketplace, "
            "or explicitly allow sending it to the selected provider for this request. Nothing was sent."
        )

    if requested in {"openai", "openai-compatible"}:
        return Route("openai", provider_label("openai"), "OpenAI-compatible endpoint.", remote=True)

    account = "grok"
    has_key = bool(keystore.load(account))
    if requested in {"grok", "auto"} and has_key and online is not False:
        return Route("grok", provider_label("grok"), "Grok (xAI), using the key in your keyring.", remote=True)
    if requested in {"grok", "auto"}:
        reason = "No Grok key is stored, so this answer is local." if not has_key else "The network is unavailable, so this answer is local."
        chosen = local(reason)
        if chosen is not None:
            return chosen
    from vital_assistant import AssistantError, _connect_help

    if requested == "grok" and not has_key:
        raise AssistantError(_connect_help("grok"))
    raise AssistantError("No provider is available. Add a Grok key or install the local model.")


def _missing_local():
    from vital_assistant import AssistantError

    return AssistantError(
        "The local model is not installed. "
        "Install “Vital Local Model” from Vital Marketplace. "
        "It downloads the official Qwen3-0.6B Q8 GGUF and llama.cpp after checking their SHA-256."
    )


def apply_route(settings, route: Route):
    from vital_assistant import Settings

    updated = Settings(**{field: getattr(settings, field) for field in Settings.__dataclass_fields__})
    updated.provider = "openai" if route.provider == "openai" else route.provider
    if route.provider == "local":
        updated.model = updated.model or "qwen3"
    return updated


def history_path() -> Path:
    return state_dir() / "history.jsonl"


def append_history(record: dict) -> None:
    if os.environ.get("VITAL_ASSISTANT_HISTORY") == "0":
        return
    try:
        from vital_assistant import load_settings

        if not load_settings().history_enabled:
            return
    except Exception:
        return
    safe = {}
    for key, value in record.items():
        if str(key).lower() in {"api_key", "authorization", "secret", "password"}:
            continue
        safe[key] = value
    safe.setdefault("ts", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    path = history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = redact(json.dumps(safe, ensure_ascii=False))
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def read_history(limit: int = 40) -> list[dict]:
    path = history_path()
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows[-limit:]


def clear_history() -> None:
    path = history_path()
    if path.exists():
        path.unlink()


def _offline(exc: Exception) -> bool:
    text = str(exc).lower()
    return "could not reach" in text or "timed out" in text or "timed out" in text


def iter_answer(
    question: str,
    settings,
    keystore,
    *,
    consent: Consent | None = None,
    payload: dict | None = None,
    shell: dict | None = None,
    mode: str = "answer",
    online: bool | None = None,
    actions_enabled: bool | None = None,
    runner=None,
):
    """Yield event dicts: provider, disclosure, token, confirm, suggestion, done, error."""

    from vital_assistant import AssistantError, make_provider, parse_reply, suggest
    from vital_local import local_ready

    consent = consent or Consent()
    enabled = settings.actions_enabled if actions_enabled is None else actions_enabled
    try:
        chosen = route_provider(settings, keystore, consent, online=online)
    except AssistantError as exc:
        yield {"event": "error", "message": str(exc)}
        return

    def events_for(route: Route):
        routed = apply_route(settings, route)
        local_text = route.provider == "local"
        bundle = assemble_context(consent, payload, local_text_only=local_text)
        yield {
            "event": "provider",
            "provider": route.provider,
            "label": route.label,
            "reason": route.reason,
            "remote": route.remote,
        }
        yield {
            "event": "disclosure",
            "text": disclosure(consent, route.label, route.remote),
            "kinds": bundle.kinds,
            "notes": bundle.notes,
        }
        user = question.strip()
        extra = []
        if bundle.text:
            extra.append(bundle.text)
        if shell and (settings.send_context or mode == "explain"):
            block = shell_block(shell)
            if block:
                extra.append(block)
        if extra:
            user = user + "\n\n" + "\n\n".join(extra)
        if mode == "command":
            try:
                suggestion = suggest(question, routed, keystore, shell if settings.send_context else None)
            except AssistantError as exc:
                if route.provider == "grok" and _offline(exc) and local_ready(settings.local_device):
                    yield {"event": "fallback", "reason": "Could not reach Grok. Answering on this computer."}
                    yield from events_for(
                        Route("local", provider_label("local"), "Grok was unreachable, so this answer is local.", False)
                    )
                    return
                yield {"event": "error", "message": str(exc)}
                return
            yield {
                "event": "suggestion",
                "command": suggestion.command,
                "explanation": suggestion.explanation,
                "risk": suggestion.risk,
            }
            yield {
                "event": "done",
                "text": suggestion.explanation,
                "provider": route.provider,
                "label": route.label,
            }
            return

        system = EXPLAIN_PROMPT if mode == "explain" else ANSWER_PROMPT
        content: str | list = user
        if bundle.image_path and route.remote:
            encoded = _image_content(bundle.image_path)
            if encoded:
                content = [{"type": "text", "text": user}, encoded]
            else:
                yield {"event": "token", "text": "The screenshot was too large to attach.\n"}
        messages = [{"role": "system", "content": system}, {"role": "user", "content": content}]
        tools = tool_schema() if enabled and mode == "answer" else None
        text_parts: list[str] = []
        calls: list[tuple[str, dict]] = []
        try:
            provider = make_provider(routed, keystore)
            for kind, piece in provider.stream(messages, tools):
                if kind == "text":
                    text_parts.append(piece)
                elif kind == "tool" and isinstance(piece, tuple):
                    calls.append(piece)
        except AssistantError as exc:
            if route.provider == "grok" and _offline(exc) and local_ready(settings.local_device):
                yield {"event": "fallback", "reason": "Could not reach Grok. Answering on this computer."}
                yield from events_for(
                    Route("local", provider_label("local"), "Grok was unreachable, so this answer is local.", False)
                )
                return
            yield {"event": "error", "message": str(exc)}
            return
        except Exception as exc:  # noqa: BLE001 - provider bugs should be a user-facing error
            yield {"event": "error", "message": f"The provider failed: {exc}"}
            return

        raw_text = _strip_think("".join(text_parts))
        visible, parsed_actions = parse_action_lines(raw_text)
        calls.extend(parsed_actions)
        if visible:
            step = 48
            for index in range(0, len(visible), step):
                yield {"event": "token", "text": visible[index : index + step]}
        command, explanation = parse_reply(visible)
        if command:
            from vital_assistant import command_risk

            yield {
                "event": "suggestion",
                "command": command,
                "explanation": explanation or visible,
                "risk": command_risk(command),
            }
        confirmed: list[dict] = []
        if enabled and calls:
            call_name, call_args = calls[0]
            try:
                plan = plan_action(call_name, call_args)
            except ActionError as exc:
                yield {"event": "error", "message": str(exc)}
                return
            if plan.mutating:
                yield {"event": "confirm", "plan": plan.to_dict()}
                append_history(
                    {
                        "role": "assistant",
                        "provider": route.provider,
                        "text": visible[:4000],
                        "context": bundle.kinds,
                        "pending_action": plan.name,
                    }
                )
                yield {"event": "done", "text": visible, "provider": route.provider, "label": route.label}
                return
            try:
                result = execute_plan(plan, True, runner or SubprocessRunner())
            except ActionError as exc:
                yield {"event": "error", "message": str(exc)}
                return
            confirmed.append({"name": plan.name, "output": result.output[:2000]})
            yield {"event": "status", "name": plan.name, "output": result.output[:2000]}
        append_history(
            {
                "role": "user",
                "provider": route.provider,
                "text": question[:4000],
                "context": bundle.kinds,
            }
        )
        append_history(
            {
                "role": "assistant",
                "provider": route.provider,
                "label": route.label,
                "text": visible[:4000],
                "context": bundle.kinds,
                "status": confirmed,
            }
        )
        yield {"event": "done", "text": visible, "provider": route.provider, "label": route.label}

    yield from events_for(chosen)


def approve_action(plan_data: dict, approved: bool, runner=None) -> dict:
    """Rebuild the plan from name and args, then run it only if approved."""

    try:
        plan = plan_action(str(plan_data.get("name", "")), plan_data.get("args") if isinstance(plan_data.get("args"), dict) else {})
    except ActionError as exc:
        log_action({"action": "invalid", "approved": False, "error": str(exc)})
        raise
    result = execute_plan(plan, approved, runner or SubprocessRunner())
    return {"code": result.code, "output": result.output, "executed": result.executed, "argv": plan.argv}


def collect(events) -> dict:
    """Fold a generator of events into one object. Used by tests and the CLI."""

    folded = {"text": "", "events": [], "error": "", "provider": "", "label": "", "plan": None, "suggestion": None}
    for event in events:
        folded["events"].append(event)
        kind = event.get("event")
        if kind == "token":
            folded["text"] += event.get("text", "")
        elif kind == "done":
            folded["text"] = event.get("text") or folded["text"]
            folded["provider"] = event.get("provider", folded["provider"])
            folded["label"] = event.get("label", folded["label"])
        elif kind == "provider":
            folded["provider"] = event.get("provider", "")
            folded["label"] = event.get("label", "")
            folded["reason"] = event.get("reason", "")
        elif kind == "error":
            folded["error"] = event.get("message", "")
        elif kind == "confirm":
            folded["plan"] = event.get("plan")
        elif kind == "suggestion":
            folded["suggestion"] = event
        elif kind == "disclosure":
            folded["disclosure"] = event.get("text", "")
    return folded


def preview_runner() -> RecordingRunner:
    return RecordingRunner()


def _strip_think(text: str) -> str:
    import re

    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _image_content(path: str) -> dict | None:
    import base64

    file = Path(path)
    if not file.is_file() or file.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        return None
    data = file.read_bytes()
    if len(data) > 1_500_000:
        return None
    kind = "jpeg" if file.suffix.lower() in {".jpg", ".jpeg"} else file.suffix.lower().lstrip(".")
    encoded = base64.b64encode(data).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:image/{kind};base64,{encoded}"}}
