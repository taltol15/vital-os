#!/bin/bash
# Headless smoke test for the Vital Assistant daemon and confirmation gate.
# A full ISO boot is separate: tools/assistant-qemu-smoke.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export VITAL_ASSISTANT_PROVIDER=mock
export VITAL_ASSISTANT_KEYSTORE=memory
export VITAL_ASSISTANT_HISTORY=0
export VITAL_ASSISTANT_NO_DBUS=1
export VITAL_ASSISTANT_STATE_DIR="${TMPDIR:-/tmp}/vital-assistant-smoke-state"
export VITAL_ASSISTANT_RUNTIME_DIR="${TMPDIR:-/tmp}/vital-assistant-smoke-run"
rm -rf "$VITAL_ASSISTANT_STATE_DIR" "$VITAL_ASSISTANT_RUNTIME_DIR"
mkdir -p "$VITAL_ASSISTANT_STATE_DIR" "$VITAL_ASSISTANT_RUNTIME_DIR"
chmod 700 "$VITAL_ASSISTANT_STATE_DIR" "$VITAL_ASSISTANT_RUNTIME_DIR"

python3 - <<'PY'
import os
import threading
from pathlib import Path
import sys

sys.path.insert(0, "apps/vital-assistant")
from vital_daemon import call, call_events, serve

socket_path = Path(os.environ["VITAL_ASSISTANT_RUNTIME_DIR"]) / "ipc.sock"
ready = threading.Event()
threading.Thread(target=lambda: serve(socket_path, ready), daemon=True).start()
if not ready.wait(5):
    raise SystemExit("daemon did not open a socket")
events = call_events("ask", {"question": "install vim", "mode": "answer"}, path=socket_path)
plans = [event for event in events if event.get("event") == "confirm"]
if not plans:
    raise SystemExit(f"expected a confirmation, got {events}")
plan = plans[0]["plan"]
if plan["argv"][:1] != ["pkexec"] or "bash" in plan["argv"]:
    raise SystemExit(f"unexpected argv {plan['argv']}")
try:
    call("approve", {"plan": {**plan, "argv": ["bash", "-lc", "true"]}, "approved": False}, path=socket_path)
except Exception as exc:
    if "Cancelled" not in str(exc) and "Nothing was changed" not in str(exc):
        raise
else:
    raise SystemExit("cancel should not run the action")
print("smoke: confirmation held and a forged argv was not run")
PY

printf 'y\n' | python3 apps/vital-assistant/vital ask "how do I delete a folder" | tee /tmp/vital-assistant-pipe.txt
if grep -q 'Running\.' /tmp/vital-assistant-pipe.txt; then
    echo "smoke: a pipe confirmed a command" >&2
    exit 1
fi
if ! grep -q 'Not run' /tmp/vital-assistant-pipe.txt; then
    echo "smoke: pipe did not refuse to run" >&2
    exit 1
fi
echo "smoke: pipe refused to execute"
echo "smoke: ok"
