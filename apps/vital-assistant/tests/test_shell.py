"""Bash and zsh integration never executes a suggestion on its own."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VITAL = ROOT / "vital"
HOOK = ROOT / "hook.bash"
ZSH = ROOT / "hook.zsh"
INSTALLER = ROOT.parents[1] / "marketplace" / "catalog" / "examples" / "vital-local-model.sh"


class ShellTests(unittest.TestCase):
    def test_bash_hook_parses_and_does_not_define_an_executor(self) -> None:
        subprocess.run(["bash", "-n", str(HOOK)], check=True)
        text = HOOK.read_text(encoding="utf-8")
        self.assertIn("</dev/null", text)
        self.assertNotIn("eval ", text)
        completed = subprocess.run(
            ["bash", "--noprofile", "--norc", "-c", f'source "{HOOK}"; type ask; type _vital_assistant_hook_on'],
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertIn("ask is a function", completed.stdout)

    def test_hook_stays_quiet_when_shell_hook_is_off(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            config = home / ".config" / "vitalos"
            config.mkdir(parents=True)
            (config / "assistant.conf").write_text("shell_hook=0\nprovider=mock\n", encoding="utf-8")
            bindir = home / "bin"
            bindir.mkdir()
            fake = bindir / "vital"
            fake.write_text("#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$HOME/called\"\n", encoding="utf-8")
            fake.chmod(0o755)
            script = textwrap.dedent(
                f"""
                set +e
                source "{HOOK}"
                _vital_assistant_record
                """
            )
            env = os.environ.copy()
            env["HOME"] = str(home)
            env["PATH"] = f"{bindir}:{env.get('PATH', '')}"
            env["PS1"] = "$ "
            subprocess.run(
                ["bash", "--noprofile", "--norc", "-c", script],
                check=False,
                env=env,
                text=True,
            )
            self.assertFalse((home / "called").exists())

    def test_failed_hook_asks_and_closes_stdin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            config = home / ".config" / "vitalos"
            config.mkdir(parents=True)
            (config / "assistant.conf").write_text("shell_hook=1\n", encoding="utf-8")
            bindir = home / "bin"
            bindir.mkdir()
            fake = bindir / "vital"
            fake.write_text(
                "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$HOME/called\"\n"
                "if [ -t 0 ]; then echo tty >> \"$HOME/called\"; fi\n",
                encoding="utf-8",
            )
            fake.chmod(0o755)
            runtime = home / "run"
            runtime.mkdir()
            script = textwrap.dedent(
                f"""
                set +e
                cd "{home}"
                source "{HOOK}"
                false
                _vital_assistant_record
                """
            )
            env = os.environ.copy()
            env["HOME"] = str(home)
            env["PATH"] = f"{bindir}:{env.get('PATH', '')}"
            env["XDG_RUNTIME_DIR"] = str(runtime)
            subprocess.run(["bash", "--noprofile", "--norc", "-c", script], check=False, env=env, text=True)
            called = (home / "called").read_text(encoding="utf-8")
            self.assertIn("--from-hook", called)
            self.assertNotIn("tty", called)

    def test_pipe_cannot_confirm_a_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env["HOME"] = tmp
            env["VITAL_ASSISTANT_PROVIDER"] = "mock"
            env["VITAL_ASSISTANT_KEYSTORE"] = "memory"
            env["VITAL_ASSISTANT_HISTORY"] = "0"
            env["VITAL_ASSISTANT_STATE_DIR"] = str(Path(tmp) / "state")
            completed = subprocess.run(
                [sys.executable, str(VITAL), "ask", "how do I delete a folder"],
                input=b"y\n",
                capture_output=True,
                env=env,
                check=False,
                start_new_session=True,
            )
        self.assertEqual(completed.returncode, 0)
        self.assertIn(b"Not run", completed.stdout)
        self.assertNotIn(b"Running.", completed.stdout)
        self.assertIn(b"rmdir empty-folder", completed.stdout)

    def test_zsh_hook_parses(self) -> None:
        zsh = subprocess.run(["zsh", "-n", str(ZSH)], check=False, capture_output=True, text=True)
        self.assertEqual(zsh.returncode, 0, zsh.stderr)
        text = ZSH.read_text(encoding="utf-8")
        self.assertIn("</dev/null", text)
        self.assertIn("add-zsh-hook", text)

    def test_installer_dry_run_matches_the_pin_file(self) -> None:
        import json

        pins = json.loads((ROOT / "local-model.json").read_text(encoding="utf-8"))
        completed = subprocess.run(
            ["sh", str(INSTALLER)],
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "VITAL_LOCAL_MODEL_DRY_RUN": "1"},
        )
        lines = dict(line.split(" ", 1) for line in completed.stdout.splitlines() if " " in line)
        self.assertEqual(lines["cpu"], pins["runtime"]["cpu"]["sha256"])
        self.assertEqual(lines["vulkan"], pins["runtime"]["vulkan"]["sha256"])
        self.assertEqual(lines["model"], pins["model"]["sha256"])
        self.assertEqual(lines["model_name"], pins["model"]["filename"])
        self.assertTrue(stat.S_ISREG(INSTALLER.stat().st_mode))


if __name__ == "__main__":
    unittest.main()
