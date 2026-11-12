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
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
EPOCH = "1700000000"
DEST = REPO / "marketplace" / "catalog" / "debs" / f"vital-assistant_{VERSION}_all.deb"

CONTROL = f"""Package: vital-assistant
Version: {VERSION}
Section: utils
Priority: optional
Architecture: all
Depends: python3, python3-gi, python3-dbus, gir1.2-gtk-4.0, gir1.2-adw-1, gir1.2-secret-1, gir1.2-glib-2.0
Recommends: policykit-1, curl, ca-certificates, gnome-shell
Maintainer: Vital OS <vitalos@localhost>
Description: System-wide Vital Assistant
 Terminal, overlay, and settings share one per-user daemon.
 API keys stay in the system keyring. Prompts are not sent to vital-os.org.
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
    for name in ("postinst", "prerm"):
        place(tree, f"DEBIAN/{name}", ROOT / name, 0o755)
    (debian / "conffiles").write_text("/etc/vital/assistant.conf\n", encoding="utf-8")
    modules = [
        "vital_assistant.py",
        "vital_actions.py",
        "vital_context.py",
        "vital_core.py",
        "vital_daemon.py",
        "vital_i18n.py",
        "vital_local.py",
        "vital_ui.py",
    ]
    place(tree, "usr/bin/vital", ROOT / "vital", 0o755)
    place(tree, "usr/bin/vital-assistant", ROOT / "vital-assistant", 0o755)
    place(tree, "usr/bin/vital-assistant-daemon", ROOT / "vital-assistant-daemon", 0o755)
    place(tree, "usr/libexec/vital-assistant-helper", ROOT / "vital-assistant-helper", 0o755)
    installer = REPO / "marketplace" / "catalog" / "examples" / "vital-local-model.sh"
    place(tree, "usr/libexec/vital-assistant-install-model", installer, 0o755)
    for module in modules:
        place(tree, f"usr/lib/vitalos/{module}", ROOT / module, 0o644)
    place(tree, "usr/share/vitalos/assistant/assistant.css", ROOT / "assistant.css", 0o644)
    place(tree, "usr/share/vitalos/assistant/local-model.json", ROOT / "local-model.json", 0o644)
    place(tree, "usr/share/applications/vital-assistant.desktop", ROOT / "vital-assistant.desktop", 0o644)
    place(tree, "usr/share/icons/hicolor/scalable/apps/vital-assistant.svg", ROOT / "vital-assistant.svg", 0o644)
    place(tree, "usr/share/vitalos/assistant/hook.bash", ROOT / "hook.bash", 0o644)
    place(tree, "usr/share/vitalos/assistant/hook.zsh", ROOT / "hook.zsh", 0o644)
    place(tree, "etc/profile.d/vital-assistant.sh", ROOT / "profile.sh", 0o644)
    place(tree, "etc/vital/assistant.conf", ROOT / "assistant.conf", 0o644)
    place(tree, "etc/dconf/db/local.d/02-vital-assistant", ROOT / "dconf.ini", 0o644)
    place(tree, "usr/share/polkit-1/actions/org.vitalos.assistant.policy", ROOT / "org.vitalos.assistant.policy", 0o644)
    place(tree, "usr/lib/systemd/user/vital-assistant.service", ROOT / "vital-assistant.service", 0o644)
    place(tree, "usr/share/dbus-1/services/org.vitalos.Assistant.service", ROOT / "org.vitalos.Assistant.service", 0o644)
    wants = tree / "usr/lib/systemd/user/default.target.wants"
    wants.mkdir(parents=True, exist_ok=True)
    link = wants / "vital-assistant.service"
    if not link.exists():
        link.symlink_to("../vital-assistant.service")
    extension = tree / "usr/share/gnome-shell/extensions/vital-assistant@vitalos"
    shutil.copytree(ROOT / "gnome-shell" / "vital-assistant@vitalos", extension)
    for path in extension.rglob("*"):
        if path.is_file():
            os.chmod(path, 0o644)
    # Do not compile gschemas here. glib-compile-schemas output depends on the
    # host GLib, so the deb hash would change between machines. postinst compiles
    # the schema on the installed system.
    doc = REPO / "docs" / "assistant.md"
    if doc.is_file():
        place(tree, "usr/share/doc/vital-assistant/assistant.md", doc, 0o644)
    for path in tree.rglob("*"):
        os.utime(path, (int(EPOCH), int(EPOCH)), follow_symlinks=False)
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
