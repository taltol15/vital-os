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
    config/calamares/modules/mount.conf
    config/calamares/modules/welcome.conf
    config/calamares/runtime/mount/main.py
    config/calamares/branding/vitalos/branding.desc
    config/calamares/branding/vitalos/show.qml
    branding/logo/vital-symbol.svg
    branding/logo/vital-wordmark.svg
    branding/logo/vital-lockup.svg
    branding/wallpapers/nocturne.svg
    branding/wallpapers/nocturne-arc.svg
    branding/wallpapers/nocturne-day.svg
    branding/logo/vital-symbol-mono.svg
    branding/logo/vital-symbol-accent.svg
    branding/logo/vital-wordmark-mono.svg
    branding/plymouth/vitalos.script
    branding/gnome-shell/gnome-shell.css
    branding/gtk/dark.css
    branding/gtk/light.css
    apps/vital-welcome/vital-welcome
    apps/vital-welcome/identity.py
    apps/vital-marketplace/vital-marketplace
    apps/vital-marketplace/vital-marketplace-helper
    marketplace/cli/vital-market
    marketplace/python/vital_catalog.py
    marketplace/schema/catalog-item.schema.json
    marketplace/schema/catalog.schema.json
    marketplace/catalog/catalog.json
    marketplace/server/vital_market/app.py
    overlay/etc/vital/marketplace.conf
    overlay/etc/vital/telemetry.conf
    apps/vital-telemetry/vital-telemetry
    apps/vital-telemetry/vital-telemetry-ctl
    apps/vital-telemetry/vital_telemetry.py
    apps/vital-assistant/vital
    apps/vital-assistant/vital-assistant
    apps/vital-assistant/vital_assistant.py
    apps/vital-assistant/build_deb.py
    PRIVACY.md
    overlay/usr/share/applications/vital-marketplace.desktop
    overlay/etc/casper.conf
    overlay/etc/dconf/db/local.d/01-vital-desktop
)
for path in "${required[@]}"; do
    [[ -f "$path" ]] || bad "missing ${path}"
done

if ! grep -q 'export FLAVOUR=' overlay/etc/casper.conf; then
    bad "casper.conf must set FLAVOUR or the live username is rewritten"
fi

if ! grep -q 'requiredStorage: 16.0' config/calamares/modules/welcome.conf; then
    bad "welcome.conf requiredStorage must be the decimal 16.0 so Calamares does not ignore it"
fi
if ! grep -q 'requiredRam: 2.0' config/calamares/modules/welcome.conf; then
    bad "welcome.conf requiredRam must be the decimal 2.0 so Calamares does not ignore it"
fi
if ! grep -q 'class MountError' config/calamares/runtime/mount/main.py; then
    bad "Calamares mount module must refuse to continue when the target disk is not mounted"
fi
if ! grep -q 'shellprocess@vital-target' config/calamares/settings.conf; then
    bad "settings.conf must run the target-disk check before unpackfs"
fi
if ! grep -q 'Package: grub-efi-amd64-signed' config/apt-preferences; then
    bad "apt pin must keep Ubuntu's signed GRUB out of the image"
fi
if grep -q '^eject$' config/packages.live.list config/calamares/modules/packages.conf; then
    bad "eject must stay installed; nautilus depends on it"
fi
if ! grep -q '^0.2.1$' VERSION; then
    bad "VERSION is not 0.2.1"
fi
for stamped in overlay/etc/issue overlay/etc/issue.net overlay/etc/motd overlay/etc/vitalos-release overlay/etc/gdm3/greeter.dconf-defaults branding/grub/theme.txt config/calamares/branding/vitalos/branding.desc config/calamares/branding/vitalos/show.qml; do
    if ! grep -q '@VERSION@' "$stamped"; then
        bad "${stamped} must take its version from @VERSION@"
    fi
    if grep -q '0\.1\.0' "$stamped"; then
        bad "${stamped} still hardcodes 0.1.0"
    fi
done
if ! grep -q 'SetDisplayPasswordFunction' branding/plymouth/vitalos.script; then
    bad "Plymouth theme must style the disk-unlock prompt"
fi
if ! grep -q 'vital-assistant' marketplace/catalog/sources/vital-assistant.json; then
    bad "Marketplace catalog is missing vital-assistant"
fi
if ! grep -q 'apps/vital-assistant/build_deb.py' build.sh; then
    bad "the ISO build must create the vital-assistant package; the deb is not stored in git"
fi
if ! grep -q 'vital-assistant.deb is missing' build/in-chroot/configure-system.sh; then
    bad "configure-system.sh must refuse to finish when vital-assistant.deb is missing"
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
    overlay/usr/libexec/vitalos-install-check
    overlay/usr/libexec/vitalos-install-bootloader
    apps/vital-assistant/profile.sh
    apps/vital-assistant/hook.bash
    overlay/etc/grub.d/06_vital_font
    overlay/usr/share/initramfs-tools/scripts/casper-bottom/26vitalos_desktop
)
for script in "${scripts[@]}"; do
    if [[ ! -x "$script" ]]; then
        bad "${script} is not executable"
    fi
    bash -n "$script" || bad "bash -n failed for ${script}"
done

python3 -m py_compile \
    apps/vital-welcome/vital-welcome \
    apps/vital-welcome/identity.py \
    apps/vital-marketplace/vital-marketplace \
    apps/vital-marketplace/vital-marketplace-helper \
    marketplace/python/vital_catalog.py \
    marketplace/cli/vital-market \
    marketplace/tools/build_catalog.py \
    marketplace/server/vital_market/app.py \
    marketplace/server/vital_market/mgmt.py \
    apps/vital-telemetry/vital-telemetry \
    apps/vital-telemetry/vital-telemetry-ctl \
    apps/vital-telemetry/vital_telemetry.py \
    apps/vital-assistant/vital \
    apps/vital-assistant/vital-assistant \
    apps/vital-assistant/vital_assistant.py \
    apps/vital-assistant/build_deb.py \
    tools/render_previews.py \
    config/calamares/runtime/mount/main.py

note "checking catalog.json"
python3 marketplace/tools/build_catalog.py --check || bad "catalog.json does not match sources"

(
    cd apps/vital-welcome
    python3 -m unittest test_identity.py
) || bad "welcome identity tests failed"

(
    cd apps/vital-assistant
    python3 -m unittest tests.test_assistant
) || bad "assistant tests failed"

if python3 -c "import fastapi, jsonschema, cryptography, pytest" >/dev/null 2>&1; then
    note "running marketplace tests"
    python3 -m pytest marketplace/server/tests marketplace/python/tests -q || bad "marketplace tests failed"
elif [[ "${VITAL_REQUIRE_MARKET_TESTS:-}" == "1" ]]; then
    bad "marketplace test dependencies are not installed"
else
    note "marketplace pytest dependencies are not installed; skipped"
fi

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
