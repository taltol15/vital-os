#!/usr/bin/env python3
"""Build a reproducible vital-assistant deb for the catalog and the ISO."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
VERSION = (REPO / "VERSION").read_text(encoding="utf-8").strip()
EPOCH = "1700000000"
DEST = REPO / "marketplace" / "catalog" / "debs" / f"vital-assistant_{VERSION}_all.deb"

CONTROL = f"""Package: vital-assistant
Version: {VERSION}
Section: utils
Priority: optional
Architecture: all
Depends: python3, python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1, gir1.2-secret-1
Maintainer: Vital OS <vitalos@localhost>
Description: Ask Vital OS for a command and confirm before it runs
 Terminal and GTK assistant. API keys stay in the system keyring.
 Prompts are not sent to vital-os.org.
"""


def place(tree: Path, relative: str, source: Path, mode: int) -> None:
    target = tree / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    os.chmod(target, mode)


def build() -> Path:
    work = Path("/tmp") / f"vital-assistant-deb-{VERSION}"
    if work.exists():
        shutil.rmtree(work)
    tree = work / "pkg"
    debian = tree / "DEBIAN"
    debian.mkdir(parents=True)
    (debian / "control").write_text(CONTROL, encoding="utf-8")
    os.chmod(debian / "control", 0o644)
    place(tree, "usr/bin/vital", ROOT / "vital", 0o755)
    place(tree, "usr/bin/vital-assistant", ROOT / "vital-assistant", 0o755)
    place(tree, "usr/lib/vitalos/vital_assistant.py", ROOT / "vital_assistant.py", 0o644)
    place(tree, "usr/share/applications/vital-assistant.desktop", ROOT / "vital-assistant.desktop", 0o644)
    place(tree, "usr/share/icons/hicolor/scalable/apps/vital-assistant.svg", ROOT / "vital-assistant.svg", 0o644)
    place(tree, "usr/share/vitalos/assistant/hook.bash", ROOT / "hook.bash", 0o644)
    place(tree, "usr/share/vitalos/assistant/hook.zsh", ROOT / "hook.zsh", 0o644)
    place(tree, "etc/profile.d/vital-assistant.sh", ROOT / "profile.sh", 0o644)
    place(tree, "etc/vital/assistant.conf", ROOT / "assistant.conf", 0o644)
    place(tree, "etc/dconf/db/local.d/02-vital-assistant", ROOT / "dconf.ini", 0o644)
    for path in tree.rglob("*"):
        os.utime(path, (int(EPOCH), int(EPOCH)))
    DEST.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["SOURCE_DATE_EPOCH"] = EPOCH
    subprocess.run(
        ["dpkg-deb", "--root-owner-group", "-Zgzip", "-z9", "--build", str(tree), str(DEST)],
        check=True,
        env=env,
    )
    os.utime(DEST, (int(EPOCH), int(EPOCH)))
    shutil.rmtree(work)
    return DEST


def main() -> int:
    path = build()
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
