"""Allowlist, confirmation, and the refusal of a root shell."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vital_actions import (  # noqa: E402
    ActionError,
    ActionPlan,
    RecordingRunner,
    confirmation_text,
    execute_plan,
    log_action,
    parse_action_lines,
    plan_action,
    redact,
)
from vital_assistant import MemoryKeyStore, Settings  # noqa: E402
from vital_context import Consent, assemble_context, disclosure  # noqa: E402
from vital_core import approve_action, collect, iter_answer, route_provider  # noqa: E402


class AllowlistTests(unittest.TestCase):
    def test_unknown_action_is_refused(self) -> None:
        with self.assertRaises(ActionError):
            plan_action("shell.run", {"command": "id"})

    def test_package_injection_is_refused(self) -> None:
        for name in ("vim;rm", "vim && true", "-y", "../vim", "VIM"):
            with self.assertRaises(ActionError):
                plan_action("apps.install", {"source": "apt", "name": name})

    def test_gnome_setting_outside_the_list_is_refused(self) -> None:
        with self.assertRaises(ActionError):
            plan_action(
                "gnome.set",
                {"schema": "org.gnome.desktop.interface", "key": "gtk-theme", "value": "Yaru"},
            )

    def test_dark_mode_plan_is_exact_and_not_privileged(self) -> None:
        plan = plan_action(
            "gnome_set",
            {"schema": "org.gnome.desktop.interface", "key": "color-scheme", "value": "prefer-dark"},
        )
        self.assertEqual(plan.argv, ["gsettings", "set", "org.gnome.desktop.interface", "color-scheme", "prefer-dark"])
        self.assertTrue(plan.mutating)
        self.assertFalse(plan.privileged)
        self.assertIn("gsettings", confirmation_text(plan))
        self.assertIn("prefer-dark", confirmation_text(plan))

    def test_install_uses_polkit_and_not_a_shell(self) -> None:
        plan = plan_action("apps.install", {"source": "apt", "name": "vim"})
        self.assertEqual(plan.argv[0], "pkexec")
        self.assertEqual(plan.argv[2:], ["install-apt", "vim"])
        self.assertTrue(plan.privileged)
        self.assertNotIn("bash", plan.argv)
        self.assertIn("polkit", confirmation_text(plan))

    def test_mutating_plan_does_not_run_until_approved(self) -> None:
        plan = plan_action("app.open", {"name": "files"})
        runner = RecordingRunner()
        with self.assertRaises(ActionError):
            execute_plan(plan, False, runner, log=False)
        self.assertEqual(runner.calls, [])
        result = execute_plan(plan, True, runner, log=False)
        self.assertTrue(result.executed)
        self.assertEqual(runner.calls, [["gtk-launch", "org.gnome.Nautilus.desktop"]])

    def test_client_argv_is_ignored_and_rebuilt(self) -> None:
        runner = RecordingRunner(output="ok")
        forged = {
            "name": "status.disk",
            "args": {},
            "argv": ["bash", "-lc", "rm -rf /"],
        }
        result = approve_action(forged, True, runner)
        self.assertEqual(result["argv"], ["df", "-h", "/"])
        self.assertEqual(runner.calls, [["df", "-h", "/"]])

    def test_a_direct_shell_plan_is_refused_even_if_approved(self) -> None:
        plan = ActionPlan("shell", {}, "no", ["bash", "-lc", "true"], True, True)
        with self.assertRaises(ActionError):
            execute_plan(plan, True, RecordingRunner(), log=False)

    def test_log_redacts_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "actions.log"
            log_action({"action": "status.disk", "output": "Bearer sk-supersecretvalue and xai-abcdef123456"}, path)
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("sk-supersecretvalue", text)
            self.assertNotIn("xai-abcdef123456", text)
            self.assertIn("[redacted]", text)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_redact_helper(self) -> None:
        self.assertNotIn("sk-abcdefgh", redact("token sk-abcdefghijkl"))


class CoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env = mock.patch.dict(os.environ, {"VITAL_ASSISTANT_HISTORY": "0"}, clear=False)
        self._env.start()

    def tearDown(self) -> None:
        self._env.stop()

    def test_install_request_confirms_and_does_not_run(self) -> None:
        runner = RecordingRunner()
        with mock.patch("vital_core.SubprocessRunner.run", side_effect=AssertionError("ran")):
            folded = collect(
                iter_answer("please install vim", Settings(provider="mock"), MemoryKeyStore(), mode="answer", runner=runner)
            )
        self.assertEqual(folded["plan"]["name"], "apps.install")
        self.assertEqual(folded["plan"]["argv"][2:], ["install-apt", "vim"])
        self.assertEqual(runner.calls, [])
        self.assertEqual(folded["provider"], "mock")

    def test_read_only_status_uses_the_runner(self) -> None:
        runner = RecordingRunner(output="ok")
        folded = collect(
            iter_answer("how much disk space is free", Settings(provider="mock"), MemoryKeyStore(), mode="answer", runner=runner)
        )
        self.assertEqual(runner.calls, [["df", "-h", "/"]])
        self.assertIn("ok", "".join(event.get("output", "") for event in folded["events"]))

    def test_sensitive_context_is_not_sent_without_a_local_model(self) -> None:
        with self.assertRaises(Exception) as caught:
            route_provider(Settings(provider="grok"), MemoryKeyStore(), Consent(clipboard=True))
        self.assertIn("Nothing was sent", str(caught.exception))

    def test_sensitive_context_prefers_a_local_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = root / "llama" / "cpu" / "llama-server"
            binary.parent.mkdir(parents=True)
            binary.write_text("#!/bin/sh\n", encoding="utf-8")
            binary.chmod(0o755)
            models = root / "models"
            models.mkdir()
            (models / "Qwen3-0.6B-Q8_0.gguf").write_bytes(b"gguf")
            env = {
                "VITAL_LLAMA_PREFIX": str(root / "llama"),
                "VITAL_LOCAL_MODEL_DIR": str(models),
            }
            store = MemoryKeyStore()
            store.store("grok", "sk-test-key")
            with mock.patch.dict(os.environ, env, clear=False):
                route = route_provider(Settings(provider="grok"), store, Consent(clipboard=True))
            self.assertEqual(route.provider, "local")
            self.assertFalse(route.remote)
            self.assertIn("this computer", route.label.lower())

    def test_context_is_omitted_without_consent(self) -> None:
        bundle = assemble_context(
            Consent(),
            {"clipboard": "secret clipboard", "window_title": "Inbox"},
            local_text_only=True,
        )
        self.assertEqual(bundle.text, "")
        self.assertFalse(bundle.sensitive)
        self.assertIn("No personal context", disclosure(Consent(), "Grok (xAI)", True))

    def test_consented_clipboard_is_named_in_the_disclosure(self) -> None:
        consent = Consent(clipboard=True, allow_remote=True)
        bundle = assemble_context(consent, {"clipboard": "hello"}, local_text_only=False)
        self.assertIn("hello", bundle.text)
        text = disclosure(consent, "Grok (xAI)", True)
        self.assertIn("clipboard", text)
        self.assertIn("Grok (xAI)", text)

    def test_private_key_file_is_not_attached(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "id_rsa"
            path.write_text("-----BEGIN OPENSSH PRIVATE KEY-----\nsecret\n", encoding="utf-8")
            bundle = assemble_context(Consent(files=(str(path),)), {}, local_text_only=True)
            self.assertNotIn("secret", bundle.text)
            self.assertTrue(bundle.notes)

    def test_action_line_parser(self) -> None:
        visible, calls = parse_action_lines('Hello\nACTION: {"name":"status.disk","args":{}}\n')
        self.assertEqual(visible, "Hello")
        self.assertEqual(calls, [("status.disk", {})])

    def test_offline_grok_falls_back_when_local_is_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = root / "cpu" / "llama-server"
            binary.parent.mkdir()
            binary.write_text("#!/bin/sh\n", encoding="utf-8")
            binary.chmod(0o755)
            model = root / "Qwen3-0.6B-Q8_0.gguf"
            model.write_bytes(b"gguf")
            env = {"VITAL_LLAMA_PREFIX": str(root), "VITAL_LOCAL_MODEL_DIR": str(root)}
            store = MemoryKeyStore()
            store.store("grok", "sk-test")
            with mock.patch.dict(os.environ, env, clear=False):
                route = route_provider(Settings(provider="grok"), store, Consent(), online=False)
            self.assertEqual(route.provider, "local")
            self.assertIn("network", route.reason.lower())


class SseTests(unittest.TestCase):
    def test_stream_parser_reads_tokens_and_tool_calls(self) -> None:
        from vital_assistant import OpenAICompatibleProvider

        class Response:
            def __iter__(self):
                yield b'data: {"choices":[{"delta":{"content":"Hi"}}]}\n'
                payload = {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {"index": 0, "function": {"name": "status_disk", "arguments": "{}"}}
                                ]
                            }
                        }
                    ]
                }
                yield f"data: {json.dumps(payload)}\n".encode()
                yield b"data: [DONE]\n"

            def close(self) -> None:
                return None

        provider = OpenAICompatibleProvider("Grok", "https://api.x.ai/v1", "sk-test", "grok-3")
        with mock.patch("urllib.request.urlopen", return_value=Response()):
            pieces = list(provider.stream([{"role": "user", "content": "hi"}], []))
        self.assertIn(("text", "Hi"), pieces)
        self.assertIn(("tool", ("status_disk", {})), pieces)
        sent = mock.patch  # silence linters
        del sent


if __name__ == "__main__":
    unittest.main()
