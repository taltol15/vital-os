#!/bin/bash
# Boot a built Vital OS ISO in QEMU when one exists.
# Without an ISO, run the headless daemon smoke and say the guest was not booted.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(tr -d '[:space:]' < "${ROOT}/VERSION")"
ISO="${ROOT}/build/output/VitalOS-${VERSION}-amd64.iso"

bash "${ROOT}/tools/assistant-smoke.sh"

if [[ ! -f "$ISO" ]]; then
    printf 'qemu: no ISO at %s; guest boot skipped\n' "$ISO"
    exit 0
fi
if ! command -v qemu-system-x86_64 >/dev/null 2>&1; then
    printf 'qemu: qemu-system-x86_64 is not installed; guest boot skipped\n'
    exit 0
fi

printf 'qemu: booting %s\n' "$ISO"
# Serial console only. The live image prints the GRUB banner and, given time,
# the Vital OS issue line. This does not click through the installer.
timeout 90 qemu-system-x86_64 \
    -m 2048 -smp 2 \
    -cdrom "$ISO" \
    -boot d \
    -display none \
    -serial stdio \
    -no-reboot \
    || true
printf 'qemu: guest process returned\n'
