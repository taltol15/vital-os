#!/usr/bin/env bash
# Shared helpers for the Vital OS image build.

if [[ -z "${VITAL_ROOT_DIR:-}" ]]; then
    printf 'VITAL_ROOT_DIR is not set\n' >&2
    exit 1
fi

log() {
    printf '[vital] %s\n' "$*"
}

die() {
    printf '[vital] %s\n' "$*" >&2
    exit 1
}

require_cmd() {
    local cmd
    for cmd in "$@"; do
        command -v "$cmd" >/dev/null 2>&1 || die "Missing command: ${cmd}"
    done
}

vital_version() {
    tr -d '[:space:]' < "${VITAL_ROOT_DIR}/VERSION"
}

fetch_checked() {
    local url="$1"
    local dest="$2"
    local sha="$3"
    if [[ -f "$dest" ]]; then
        if echo "${sha}  ${dest}" | sha256sum -c --status; then
            return 0
        fi
        rm -f "$dest"
    fi
    curl -fL --retry 4 --retry-delay 2 -o "$dest" "$url"
    echo "${sha}  ${dest}" | sha256sum -c --status || die "Checksum mismatch for ${dest}"
}

mount_chroot() {
    local root="$1"
    mkdir -p "${root}/dev" "${root}/proc" "${root}/sys" "${root}/run" "${root}/dev/pts"
    mount --bind /dev "${root}/dev"
    mount --bind /dev/pts "${root}/dev/pts"
    mount -t proc proc "${root}/proc"
    mount -t sysfs sysfs "${root}/sys"
    mount -t tmpfs tmpfs "${root}/run"
    if [[ -e /etc/resolv.conf ]]; then
        rm -f "${root}/etc/resolv.conf"
        cp -L /etc/resolv.conf "${root}/etc/resolv.conf"
    fi
}

umount_chroot() {
    local root="$1"
    [[ -d "$root" ]] || return 0
    umount "${root}/run" 2>/dev/null || umount -l "${root}/run" 2>/dev/null || true
    umount "${root}/sys" 2>/dev/null || umount -l "${root}/sys" 2>/dev/null || true
    umount "${root}/proc" 2>/dev/null || umount -l "${root}/proc" 2>/dev/null || true
    umount "${root}/dev/pts" 2>/dev/null || umount -l "${root}/dev/pts" 2>/dev/null || true
    umount "${root}/dev" 2>/dev/null || umount -l "${root}/dev" 2>/dev/null || true
}

read_package_list() {
    local file="$1"
    grep -E '^[[:alnum:]][[:alnum:].+-]*$' "$file"
}
