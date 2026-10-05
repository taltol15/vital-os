"""The install counter sends four fields and stays quiet when it should."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "vital-telemetry"))

from vital_telemetry import enabled, main, prepare_event, write_enabled  # noqa: E402


def _env(tmp_path: Path, monkeypatch, *, enabled_flag: str = "true", cmdline: str = "quiet") -> None:
    conf = tmp_path / "telemetry.conf"
    conf.write_text(
        f"enabled={enabled_flag}\nendpoint=https://vital-os.org/api/v1/telemetry\n",
        encoding="utf-8",
    )
    command = tmp_path / "cmdline"
    command.write_text(cmdline + "\n", encoding="utf-8")
    monkeypatch.setenv("VITAL_TELEMETRY_CONF", str(conf))
    monkeypatch.setenv("VITAL_TELEMETRY_STATE", str(tmp_path / "state"))
    monkeypatch.setenv("VITAL_TELEMETRY_CMDLINE", str(command))
    monkeypatch.setenv("VITAL_OS_VERSION", "0.1.0")
    monkeypatch.setenv("VITAL_TELEMETRY_NO_PKEXEC", "1")


def test_payload_is_only_the_four_fields(tmp_path: Path, monkeypatch) -> None:
    _env(tmp_path, monkeypatch)
    payload = prepare_event("install")
    assert payload is not None
    assert set(payload) == {"install_id", "os_version", "event", "ts"}
    assert payload["event"] == "install"
    assert payload["os_version"] == "0.1.0"
    install_id = (tmp_path / "state" / "install_id").read_text(encoding="utf-8").strip()
    assert install_id == payload["install_id"]
    assert (tmp_path / "state" / "install_id").stat().st_mode & 0o777 == 0o600


def test_opt_out_and_live_session_send_nothing(tmp_path: Path, monkeypatch) -> None:
    _env(tmp_path, monkeypatch, enabled_flag="false")
    assert prepare_event("heartbeat") is None
    assert not (tmp_path / "state" / "install_id").exists()
    _env(tmp_path, monkeypatch, cmdline="boot=casper quiet splash")
    assert prepare_event("install") is None
    assert main(["install"]) == 0
    assert not (tmp_path / "state" / "install_sent").exists()


def test_offline_failure_is_silent(tmp_path: Path, monkeypatch) -> None:
    _env(tmp_path, monkeypatch)
    conf = Path(os.environ["VITAL_TELEMETRY_CONF"])
    conf.write_text("enabled=true\nendpoint=https://127.0.0.1:9/api/v1/telemetry\n", encoding="utf-8")
    assert main(["install"]) == 0
    assert not (tmp_path / "state" / "install_sent").exists()


def test_switch_rewrites_conf(tmp_path: Path, monkeypatch) -> None:
    _env(tmp_path, monkeypatch)
    path = Path(os.environ["VITAL_TELEMETRY_CONF"])
    write_enabled(False, path)
    assert enabled(path) is False
    write_enabled(True, path)
    assert enabled(path) is True
    text = path.read_text(encoding="utf-8")
    assert "endpoint=https://vital-os.org/api/v1/telemetry" in text
