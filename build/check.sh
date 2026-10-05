#!/usr/bin/env bash
# Static checks for the Vital OS tree. Safe to run without root.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

fail=0
note() { printf 'check: %s\n' "$*"; }
bad() { printf 'check: %s\n' "$*" >&2; fail=1; }

required=(
    VERSION
    build.sh
    build/lib/common.sh
    build/in-chroot/configure-system.sh
    build/package-release.sh
    config/packages.desktop.list
    config/packages.live.list
    config/sources.env
    config/apt-preferences
    config/os-release.in
    config/grub.cfg
    config/flathub.flatpakrepo
    config/calamares/settings.conf
    config/calamares/branding/vitalos/branding.desc
    config/calamares/branding/vitalos/show.qml
    branding/logo/vital-symbol.svg
    branding/logo/vital-wordmark.svg
    branding/logo/vital-lockup.svg
    branding/wallpapers/nocturne.svg
    branding/wallpapers/nocturne-arc.svg
    branding/plymouth/vitalos.script
    branding/gnome-shell/gnome-shell.css
    branding/gtk/dark.css
    branding/gtk/light.css
    apps/vital-welcome/vital-welcome
    overlay/etc/casper.conf
    overlay/etc/dconf/db/local.d/01-vital-desktop
)
for path in "${required[@]}"; do
    [[ -f "$path" ]] || bad "missing ${path}"
done

if ! grep -q 'export FLAVOUR=' overlay/etc/casper.conf; then
    bad "casper.conf must set FLAVOUR or the live username is rewritten"
fi

while IFS= read -r pkg; do
    case "$pkg" in
        ubuntu-desktop|ubuntu-desktop-minimal|ubuntu-session|snapd|yaru-*|nvidia-*)
            bad "package list contains ${pkg}"
            ;;
    esac
done < <(grep -h -E '^[[:alnum:]]' config/packages.desktop.list config/packages.live.list)

scripts=(
    build.sh
    build/lib/common.sh
    build/in-chroot/configure-system.sh
    build/check.sh
    build/package-release.sh
    tools/qemu-boot.sh
    overlay/usr/libexec/vitalos-maybe-install
    overlay/etc/grub.d/06_vital_font
    overlay/usr/share/initramfs-tools/scripts/casper-bottom/26vitalos_desktop
)
for script in "${scripts[@]}"; do
    if [[ ! -x "$script" ]]; then
        bad "${script} is not executable"
    fi
    bash -n "$script" || bad "bash -n failed for ${script}"
done

python3 -m py_compile apps/vital-welcome/vital-welcome tools/render_previews.py

if command -v shellcheck >/dev/null 2>&1; then
    note "running shellcheck"
    shellcheck -x "${scripts[@]}" || bad "shellcheck reported issues"
else
    note "shellcheck is not installed; syntax was checked with bash -n"
fi

if [[ "$fail" -ne 0 ]]; then
    note "failed"
    exit 1
fi
note "ok"
