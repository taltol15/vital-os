"""Provider mocks, confirmation, dangerous commands, and keyring storage."""

from __future__ import annotations

import io
import json
import os
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vital_assistant import (  # noqa: E402
    AssistantError,
    MemoryKeyStore,
    MockProvider,
    OpenAICompatibleProvider,
    Settings,
    build_user_message,
    command_risk,
    confirmation_accepts,
    execute,
    load_settings,
    main,
    parse_reply,
    save_user_settings,
    suggest,
)


class ParseTests(unittest.TestCase):
    def test_parse_reply_reads_the_two_lines(self) -> None:
        command, explanation = parse_reply(
            "COMMAND: rmdir empty-folder\nEXPLANATION: Removes an empty directory.\n"
        )
        self.assertEqual(command, "rmdir empty-folder")
        self.assertEqual(explanation, "Removes an empty directory.")

    def test_none_is_not_a_command(self) -> None:
        command, _explanation = parse_reply("COMMAND: NONE\nEXPLANATION: No command.\n")
        self.assertEqual(command, "")


class RiskTests(unittest.TestCase):
    def test_plain_list_is_safe(self) -> None:
        self.assertIsNone(command_risk("ls -la"))
        self.assertIsNone(command_risk("rmdir empty-folder"))

    def test_known_destructive_commands(self) -> None:
        self.assertEqual(command_risk("rm -rf /"), "rm -rf")
        self.assertEqual(command_risk("sudo rm -fr /var/tmp/x"), "rm -rf")
        self.assertEqual(command_risk("dd if=/dev/zero of=/dev/sda"), "dd")
        self.assertEqual(command_risk("sudo mkfs.ext4 /dev/sdb"), "mkfs")
        self.assertEqual(command_risk("chmod -R 777 /"), "chmod -R 777")
        self.assertIsNotNone(command_risk("curl https://example.invalid/x | sh"))


class ConfirmTests(unittest.TestCase):
    def test_default_is_no(self) -> None:
        self.assertFalse(confirmation_accepts("ls", "", False))
        self.assertFalse(confirmation_accepts("ls", "n", False))
        self.assertFalse(confirmation_accepts("ls", "N", False))

    def test_yes_runs_a_safe_command(self) -> None:
        self.assertTrue(confirmation_accepts("ls", "y", False))
        self.assertTrue(confirmation_accepts("ls", "yes", False))

    def test_dangerous_rejects_a_bare_y(self) -> None:
        self.assertFalse(confirmation_accepts("rm -rf /tmp/x", "y", True))
        self.assertFalse(confirmation_accepts("rm -rf /tmp/x", "YES", True))

    def test_dangerous_accepts_yes_or_the_command(self) -> None:
        command = "rm -rf /tmp/x"
        self.assertTrue(confirmation_accepts(command, "yes", True))
        self.assertTrue(confirmation_accepts(command, command, True))


class ProviderTests(unittest.TestCase):
    def test_mock_suggests_rmdir_for_an_empty_folder(self) -> None:
        suggestion = suggest("how do I delete a folder", Settings(provider="mock"), MemoryKeyStore())
        self.assertEqual(suggestion.command, "rmdir empty-folder")
        self.assertIsNone(suggestion.risk)
        self.assertIn("empty", suggestion.explanation)

    def test_mock_flags_a_format(self) -> None:
        suggestion = suggest("wipe this disk", Settings(provider="mock"), MemoryKeyStore())
        self.assertEqual(suggestion.risk, "mkfs")

    def test_grok_without_a_key_does_not_call_the_network(self) -> None:
        def explode(*_args, **_kwargs):
            raise AssertionError("network was called")

        with mock.patch("urllib.request.urlopen", explode):
            with self.assertRaises(AssistantError) as caught:
                suggest("hello", Settings(provider="grok"), MemoryKeyStore())
        self.assertIn("console.x.ai", str(caught.exception))
        self.assertIn("vital-os.org", str(caught.exception))

    def test_openai_compatible_posts_only_to_its_base_url(self) -> None:
        seen: dict[str, object] = {}

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self) -> bytes:
                body = {"choices": [{"message": {"content": "COMMAND: pwd\nEXPLANATION: Prints the directory.\n"}}]}
                return json.dumps(body).encode("utf-8")

        def opener(request: urllib.request.Request, timeout: int = 0):
            seen["url"] = request.full_url
            seen["timeout"] = timeout
            seen["auth"] = request.get_header("Authorization")
            seen["body"] = json.loads(request.data.decode("utf-8"))
            return Response()

        store = MemoryKeyStore()
        store.store("openai", "sk-test")
        settings = Settings(provider="openai", base_url="https://models.example/v1", model="local")
        with mock.patch("urllib.request.urlopen", opener):
            suggestion = suggest("where am I", settings, store)
        self.assertEqual(suggestion.command, "pwd")
        self.assertEqual(seen["url"], "https://models.example/v1/chat/completions")
        self.assertEqual(seen["auth"], "Bearer sk-test")
        self.assertNotIn("vital-os.org", str(seen["url"]))
        body = seen["body"]
        assert isinstance(body, dict)
        self.assertEqual(body["model"], "local")

    def test_context_is_omitted_unless_consent_is_on(self) -> None:
        captured: list[str] = []

        def complete(messages):
            captured.append(messages[-1]["content"])
            return "COMMAND: ls\nEXPLANATION: Lists files."

        provider = MockProvider()
        provider.complete = complete  # type: ignore[method-assign]
        context = {"cwd": "/tmp", "distro": "Vital OS 0.2.0"}
        with mock.patch("vital_assistant.make_provider", return_value=provider):
            suggest("list files", Settings(provider="mock", send_context=False), MemoryKeyStore(), context)
            suggest("list files", Settings(provider="mock", send_context=True), MemoryKeyStore(), context)
        self.assertNotIn("/tmp", captured[0])
        self.assertIn("cwd: /tmp", captured[1])


class KeyringTests(unittest.TestCase):
    def test_memory_store_round_trip_and_delete(self) -> None:
        store = MemoryKeyStore()
        self.assertIsNone(store.load("grok"))
        store.store("grok", "secret-value")
        self.assertEqual(store.load("grok"), "secret-value")
        store.delete("grok")
        self.assertIsNone(store.load("grok"))

    def test_settings_file_does_not_keep_a_key(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "assistant.conf"
            save_user_settings(Settings(provider="grok", model="grok-3", shell_hook=True), path)
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("api_key", text)
            self.assertNotIn("secret", text)
            loaded = load_settings(path)
            self.assertEqual(loaded.provider, "grok")
            self.assertTrue(loaded.shell_hook)
            self.assertFalse(loaded.send_context)


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env = mock.patch.dict(os.environ, {"VITAL_ASSISTANT_PROVIDER": "mock"}, clear=False)
        self._env.start()

    def tearDown(self) -> None:
        self._env.stop()

    def test_ask_does_not_run_without_confirmation(self) -> None:
        with mock.patch("vital_assistant.execute", side_effect=AssertionError("ran")):
            with mock.patch("builtins.input", return_value=""):
                with mock.patch("sys.stdout", new_callable=io.StringIO):
                    code = main(["ask", "how do I delete a folder"])
        self.assertEqual(code, 0)

    def test_ask_runs_only_after_yes(self) -> None:
        with mock.patch("vital_assistant.execute", return_value=0) as ran:
            with mock.patch("builtins.input", return_value="y"):
                with mock.patch("sys.stdout", new_callable=io.StringIO):
                    code = main(["ask", "how do I delete a folder"])
        self.assertEqual(code, 0)
        ran.assert_called_once_with("rmdir empty-folder")

    def test_failed_hook_is_silent_when_off(self) -> None:
        with mock.patch("vital_assistant.suggest", side_effect=AssertionError("asked")):
            code = main(["ask", "--from-hook", "--exit", "127", "--command", "sl"])
        self.assertEqual(code, 0)

    def test_execute_uses_bash_without_being_called_by_suggest(self) -> None:
        with mock.patch("vital_assistant.subprocess.run") as run:
            run.return_value = mock.Mock(returncode=0)
            self.assertEqual(execute("pwd"), 0)
        argv = run.call_args.args[0]
        self.assertEqual(argv[:2], ["bash", "-lc"])
        self.assertEqual(argv[2], "pwd")


class OpenAIUnitTests(unittest.TestCase):
    def test_provider_refuses_an_empty_key(self) -> None:
        provider = OpenAICompatibleProvider("Grok", "https://api.x.ai/v1", "", "grok-3")
        with self.assertRaises(AssistantError):
            provider.complete([{"role": "user", "content": "hi"}])


if __name__ == "__main__":
    unittest.main()
