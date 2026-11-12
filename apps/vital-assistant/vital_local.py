"""Optional llama.cpp runtime and the pinned Qwen3 GGUF.

CPU is the default. A Vulkan build is used only when the user asked for a
GPU (or automatic) and that build is installed next to a render node.
The server listens on 127.0.0.1. Prompts are not written to the action log.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

PINS_NAME = "local-model.json"
_PROCESS: subprocess.Popen[bytes] | None = None
_BASE_URL = ""


def pins_path() -> Path:
    override = os.environ.get("VITAL_LOCAL_MODEL_PINS", "").strip()
    if override:
        return Path(override)
    bundled = Path("/usr/share/vitalos/assistant") / PINS_NAME
    if bundled.is_file():
        return bundled
    return Path(__file__).resolve().parent / PINS_NAME


def load_pins(path: Path | None = None) -> dict:
    return json.loads((path or pins_path()).read_text(encoding="utf-8"))


def install_roots() -> list[Path]:
    roots = []
    prefix = os.environ.get("VITAL_LLAMA_PREFIX", "").strip()
    if prefix:
        roots.append(Path(prefix))
    roots.append(Path("/usr/lib/vitalos/llama"))
    roots.append(Path("/var/lib/vitalos/llama"))
    return roots


def model_dirs() -> list[Path]:
    dirs = []
    override = os.environ.get("VITAL_LOCAL_MODEL_DIR", "").strip()
    if override:
        dirs.append(Path(override))
    dirs.append(Path("/var/lib/vitalos/models"))
    dirs.append(Path("/usr/share/vitalos/models"))
    return dirs


def _manifest() -> dict:
    for root in install_roots():
        path = root / "manifest.json"
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(data, dict):
                return data
    return {}


def find_binary(device: str) -> Path | None:
    manifest = _manifest()
    key = "vulkan_binary" if device == "gpu" else "cpu_binary"
    named = manifest.get(key) or manifest.get("binary")
    if device == "cpu" and manifest.get("cpu_binary"):
        named = manifest["cpu_binary"]
    if isinstance(named, str) and Path(named).is_file():
        return Path(named)
    folder = "vulkan" if device == "gpu" else "cpu"
    names = ("llama-server",)
    for root in install_roots():
        candidates = [root / folder, root / folder / "llama-b12212", root]
        for directory in candidates:
            for name in names:
                path = directory / name
                if path.is_file() and os.access(path, os.X_OK):
                    return path
            if directory.is_dir():
                for path in directory.rglob("llama-server"):
                    if path.is_file() and os.access(path, os.X_OK):
                        return path
    return None


def find_model() -> Path | None:
    manifest = _manifest()
    named = manifest.get("model")
    if isinstance(named, str) and Path(named).is_file():
        return Path(named)
    filename = "Qwen3-0.6B-Q8_0.gguf"
    try:
        filename = load_pins()["model"]["filename"]
    except (OSError, json.JSONDecodeError, KeyError):
        pass
    for directory in model_dirs():
        path = directory / filename
        if path.is_file():
            return path
    return None


def gpu_available() -> bool:
    dri = Path("/dev/dri")
    if not dri.is_dir():
        return False
    return any(dri.glob("renderD*"))


def choose_device(preference: str) -> str:
    choice = (preference or "auto").strip().lower()
    if choice == "cpu":
        return "cpu"
    if choice == "gpu":
        return "gpu" if find_binary("gpu") and gpu_available() else "cpu"
    if find_binary("gpu") and gpu_available():
        return "gpu"
    return "cpu"


def local_ready(preference: str = "auto") -> bool:
    device = choose_device(preference)
    return find_binary(device) is not None and find_model() is not None


def describe_local(preference: str = "auto") -> dict:
    device = choose_device(preference) if local_ready(preference) else "none"
    binary = find_binary(device) if device != "none" else None
    model = find_model()
    return {
        "ready": binary is not None and model is not None,
        "device": device if binary is not None and model is not None else "none",
        "binary": str(binary) if binary else "",
        "model": str(model) if model else "",
        "gpu": gpu_available(),
    }


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _healthy(base_url: str) -> bool:
    root = base_url[:-3] if base_url.endswith("/v1") else base_url.rstrip("/")
    try:
        with urllib.request.urlopen(root + "/health", timeout=0.4) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def ensure_server(preference: str = "auto") -> str:
    """Start llama-server on localhost if the pinned model is installed."""

    global _PROCESS, _BASE_URL
    if _BASE_URL and _healthy(_BASE_URL):
        return _BASE_URL
    info = describe_local(preference)
    if not info["ready"]:
        raise RuntimeError("local model is not installed")
    port = _free_port()
    binary = Path(info["binary"])
    command = [
        str(binary),
        "-m",
        info["model"],
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--alias",
        "qwen3",
        "--jinja",
        "--reasoning",
        "off",
        "--no-webui",
        "-c",
        "4096",
        "-ngl",
        "99" if info["device"] == "gpu" else "0",
        "-t",
        str(min(os.cpu_count() or 2, 4)),
    ]
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = str(binary.parent) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    _PROCESS = subprocess.Popen(
        command,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    _BASE_URL = f"http://127.0.0.1:{port}/v1"
    deadline = time.time() + 30
    while time.time() < deadline:
        if _PROCESS.poll() is not None:
            raise RuntimeError("llama-server exited before it was ready")
        if _healthy(f"http://127.0.0.1:{port}"):
            return _BASE_URL
        time.sleep(0.2)
    stop_server()
    raise RuntimeError("llama-server did not become ready")


def stop_server() -> None:
    global _PROCESS, _BASE_URL
    process = _PROCESS
    _PROCESS = None
    _BASE_URL = ""
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()


def server_url(preference: str = "auto") -> str:
    if _BASE_URL and _healthy(_BASE_URL.rsplit("/v1", 1)[0]):
        return _BASE_URL
    if not local_ready(preference):
        return ""
    return ensure_server(preference)
