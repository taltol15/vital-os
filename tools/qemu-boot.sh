#!/usr/bin/env bash
# Boot a built Vital OS ISO in QEMU.
# Usage: tools/qemu-boot.sh [bios|uefi]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-bios}"
VERSION="$(tr -d '[:space:]' < "${ROOT}/VERSION")"
ISO="${ROOT}/build/output/VitalOS-${VERSION}-amd64.iso"
[[ -f "$ISO" ]] || {
    printf 'ISO not found: %s\n' "$ISO" >&2
    exit 1
}
command -v qemu-system-x86_64 >/dev/null 2>&1 || {
    printf 'qemu-system-x86_64 is not installed\n' >&2
    exit 1
}

args=(
    -m 3072
    -smp 2
    -cdrom "$ISO"
    -boot d
    -vga virtio
    -serial stdio
    -netdev "user,id=net0"
    -device "virtio-net-pci,netdev=net0"
)
if [[ -e /dev/kvm ]]; then
    args+=(-enable-kvm -cpu host)
fi

case "$MODE" in
    bios)
        ;;
    uefi)
        code=""
        for candidate in \
            /usr/share/OVMF/OVMF_CODE_4M.fd \
            /usr/share/OVMF/OVMF_CODE.fd \
            /usr/share/ovmf/OVMF.fd
        do
            if [[ -f "$candidate" ]]; then
                code="$candidate"
                break
            fi
        done
        [[ -n "$code" ]] || {
            printf 'OVMF firmware not found. Install the ovmf package.\n' >&2
            exit 1
        }
        args+=(-bios "$code")
        ;;
    *)
        printf 'Usage: %s [bios|uefi]\n' "$0" >&2
        exit 1
        ;;
esac

exec qemu-system-x86_64 "${args[@]}"
