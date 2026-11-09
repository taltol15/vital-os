"""Socket IPC: one core, and approval still rebuilds the plan."""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vital_assistant import AssistantError  # noqa: E402
from vital_daemon import call, call_events, serve  # noqa: E402


class DaemonTests(unittest.TestCase):
    def test_ask_and_cancel_share_the_core(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            socket_path = Path(tmp) / "ipc.sock"
            env = {
                "VITAL_ASSISTANT_PROVIDER": "mock",
                "VITAL_ASSISTANT_KEYSTORE": "memory",
                "VITAL_ASSISTANT_HISTORY": "0",
                "VITAL_ASSISTANT_NO_DBUS": "1",
                "VITAL_ASSISTANT_STATE_DIR": str(Path(tmp) / "state"),
                "VITAL_ASSISTANT_RUNTIME_DIR": str(Path(tmp) / "run"),
            }
            ready = threading.Event()
            with mock.patch.dict(os.environ, env, clear=False):
                thread = threading.Thread(target=lambda: serve(socket_path, ready), daemon=True)
                thread.start()
                self.assertTrue(ready.wait(3))
                events = call_events(
                    "ask",
                    {"question": "install vim", "mode": "answer", "consent": {}},
                    path=socket_path,
                )
                plan = next(event["plan"] for event in events if event.get("event") == "confirm")
                self.assertEqual(plan["argv"][2:], ["install-apt", "vim"])
                plan["argv"] = ["bash", "-lc", "true"]
                with self.assertRaises(AssistantError):
                    call("approve", {"plan": plan, "approved": False}, path=socket_path)
                status = call("status", path=socket_path)
            self.assertEqual(status["provider"], "mock")
            self.assertIn("local", status)


if __name__ == "__main__":
    unittest.main()
