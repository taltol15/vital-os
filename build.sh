#!/usr/bin/env bash
# Vital OS image build.
#   ./build.sh check          static checks, no root
#   sudo ./build.sh iso       debootstrap a noble live image and wrap a hybrid ISO
#   sudo ./build.sh install-deps
set -euo pipefail

VITAL_ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=build/lib/common.sh
source "${VITAL_ROOT_DIR}/build/lib/common.sh"

WORK="${VITAL_ROOT_DIR}/build/work"
OUTPUT="${VITAL_ROOT_DIR}/build/output"
CACHE="${VITAL_ROOT_DIR}/build/cache"
ROOTFS="${WORK}/rootfs"
ISO_TREE="${WORK}/iso"
VERSION="$(vital_version)"
MIRROR="${VITAL_MIRROR:-http://archive.ubuntu.com/ubuntu}"
SQUASH_COMP="${VITAL_SQUASHFS_COMP:-xz}"
SWAP_ON=""
MOUNTED=0

cleanup() {
    local status=$?
    if [[ "$MOUNTED" -eq 1 ]]; then
        umount_chroot "$ROOTFS" || true
        MOUNTED=0
    fi
    if [[ -n "$SWAP_ON" && -f "$SWAP_ON" ]]; then
        swapoff "$SWAP_ON" || true
    fi
    if [[ "$status" -ne 0 ]]; then
        log "Build failed (exit ${status})"
    fi
    exit "$status"
}

host_packages() {
    cat <<'EOF'
debootstrap
squashfs-tools
xorriso
grub-pc-bin
grub-efi-amd64-bin
grub-common
mtools
dosfstools
ca-certificates
curl
gnupg
rsync
python3
python3-pil
librsvg2-bin
fonts-inter
fonts-ibm-plex
unzip
EOF
}

install_host_deps() {
    [[ "$(id -u)" -eq 0 ]] || die "install-deps needs root"
    local packages=()
    mapfile -t packages < <(host_packages)
    apt-get update
    apt-get install -y "${packages[@]}"
    if ! command -v shellcheck >/dev/null 2>&1; then
        apt-get install -y shellcheck || true
    fi
}

ensure_host_deps() {
    local missing=0
    local cmd
    for cmd in debootstrap mksquashfs xorriso grub-mkimage grub-mkstandalone mkfs.vfat mcopy rsync curl python3 rsvg-convert; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            printf 'missing host command: %s\n' "$cmd" >&2
            missing=1
        fi
    done
    [[ "$missing" -eq 0 ]] || die "Install host packages with: sudo ./build.sh install-deps"
    [[ -f /usr/lib/grub/i386-pc/cdboot.img ]] || die "grub-pc-bin is installed but cdboot.img is missing"
    [[ -f /usr/lib/grub/x86_64-efi/moddep.lst ]] || die "grub-efi-amd64-bin is installed but EFI modules are missing"
}

ensure_space_and_swap() {
    local avail_gb avail_mb
    avail_gb="$(df -BG --output=avail "${VITAL_ROOT_DIR}" | tail -1 | tr -dc '0-9')"
    [[ "$avail_gb" -ge 18 ]] || die "Need at least 18 GB free for the image build (have ${avail_gb} GB)"
    avail_mb="$(awk '/MemAvailable:/ {print int($2/1024)}' /proc/meminfo)"
    if [[ "$avail_mb" -lt 4096 ]]; then
        SWAP_ON="${WORK}/swapfile"
        log "Available RAM is ${avail_mb} MB; adding an 8 GB swap file"
        if [[ ! -f "$SWAP_ON" ]]; then
            if ! fallocate -l 8G "$SWAP_ON"; then
                dd if=/dev/zero of="$SWAP_ON" bs=1M count=8192 status=progress
            fi
            chmod 600 "$SWAP_ON"
            mkswap "$SWAP_ON"
        fi
        if ! swapon "$SWAP_ON"; then
            log "Could not enable the swap file on this filesystem; continuing without it"
            SWAP_ON=""
        fi
    fi
}

stage_downloads() {
    # shellcheck disable=SC1091
    source "${VITAL_ROOT_DIR}/config/sources.env"
    mkdir -p "$CACHE"
    fetch_checked "$MOZILLA_KEY_URL" "${CACHE}/packages.mozilla.org.asc" "$MOZILLA_KEY_SHA256"
    fetch_checked "$DASH_TO_DOCK_URL" "${CACHE}/dash-to-dock.zip" "$DASH_TO_DOCK_SHA256"
    fetch_checked "$PAPIRUS_FOLDERS_URL" "${CACHE}/papirus-folders" "$PAPIRUS_FOLDERS_SHA256"
    chmod 0755 "${CACHE}/papirus-folders"
}

make_wallpaper_deb() {
    local dest="$1"
    local work control
    work="$(mktemp -d)"
    mkdir -p "${work}/DEBIAN"
    control="${work}/DEBIAN/control"
    cat > "$control" <<'EOF'
Package: ubuntu-wallpapers
Version: 24.04.2+vitalos1
Section: metapackages
Priority: optional
Architecture: all
Maintainer: Vital OS <vitalos@localhost>
Provides: ubuntu-wallpapers
Description: placeholder without Ubuntu wallpaper artwork
 Ubuntu's gnome-shell package depends on the name ubuntu-wallpapers.
 Vital OS provides an empty package so those images are not installed.
EOF
    dpkg-deb --build "$work" "$dest" >/dev/null
    rm -rf "$work"
}

write_identity_files() {
    local stage="$1"
    sed "s/@VERSION@/${VERSION}/g" "${VITAL_ROOT_DIR}/config/os-release.in" > "${stage}/os-release"
    cat > "${stage}/lsb-release" <<EOF
DISTRIB_ID=VitalOS
DISTRIB_RELEASE=${VERSION}
DISTRIB_CODENAME=noble
DISTRIB_DESCRIPTION="Vital OS ${VERSION}"
EOF
}

install_brand_assets() {
    local root="$1"
    local brand="$2"
    local filled

    install -d "${root}/usr/share/backgrounds/vitalos"
    install -m 0644 "${brand}/wallpaper-nocturne.png" "${root}/usr/share/backgrounds/vitalos/nocturne.png"
    install -m 0644 "${brand}/wallpaper-arc.png" "${root}/usr/share/backgrounds/vitalos/nocturne-arc.png"
    install -m 0644 "${brand}/wallpaper-day.png" "${root}/usr/share/backgrounds/vitalos/nocturne-day.png"
    install -m 0644 "${VITAL_ROOT_DIR}/branding/wallpapers/nocturne.svg" "${root}/usr/share/backgrounds/vitalos/nocturne.svg"
    install -m 0644 "${VITAL_ROOT_DIR}/branding/wallpapers/nocturne-arc.svg" "${root}/usr/share/backgrounds/vitalos/nocturne-arc.svg"
    install -m 0644 "${VITAL_ROOT_DIR}/branding/wallpapers/nocturne-day.svg" "${root}/usr/share/backgrounds/vitalos/nocturne-day.svg"

    install -d "${root}/usr/share/pixmaps" \
        "${root}/usr/share/icons/hicolor/scalable/apps" \
        "${root}/usr/share/icons/hicolor/256x256/apps" \
        "${root}/usr/share/icons/hicolor/128x128/apps" \
        "${root}/usr/share/icons/hicolor/48x48/apps"
    install -m 0644 "${brand}/gdm-logo.png" "${root}/usr/share/pixmaps/vitalos-logo.png"
    install -m 0644 "${VITAL_ROOT_DIR}/branding/logo/vital-symbol.svg" \
        "${root}/usr/share/icons/hicolor/scalable/apps/vitalos.svg"
    install -m 0644 "${brand}/symbol-256.png" "${root}/usr/share/icons/hicolor/256x256/apps/vitalos.png"
    install -m 0644 "${brand}/symbol-128.png" "${root}/usr/share/icons/hicolor/128x128/apps/vitalos.png"
    install -m 0644 "${brand}/symbol-48.png" "${root}/usr/share/icons/hicolor/48x48/apps/vitalos.png"

    install -d "${root}/usr/share/plymouth/themes/vitalos"
    install -m 0644 "${VITAL_ROOT_DIR}/branding/plymouth/vitalos.plymouth" \
        "${root}/usr/share/plymouth/themes/vitalos/vitalos.plymouth"
    install -m 0644 "${VITAL_ROOT_DIR}/branding/plymouth/vitalos.script" \
        "${root}/usr/share/plymouth/themes/vitalos/vitalos.script"
    install -m 0644 "${brand}/plymouth-logo.png" "${root}/usr/share/plymouth/themes/vitalos/logo.png"
    install -m 0644 "${brand}/plymouth-progress.png" "${root}/usr/share/plymouth/themes/vitalos/progress.png"

    install -d "${root}/usr/share/themes/Vital/gnome-shell"
    install -m 0644 "${VITAL_ROOT_DIR}/branding/gnome-shell/gnome-shell.css" \
        "${root}/usr/share/themes/Vital/gnome-shell/gnome-shell.css"
    install -m 0644 "${brand}/lock-background.png" \
        "${root}/usr/share/themes/Vital/gnome-shell/lock-background.png"

    install -d "${root}/usr/share/grub/themes/vital"
    install -m 0644 "${VITAL_ROOT_DIR}/branding/grub/theme.txt" "${root}/usr/share/grub/themes/vital/theme.txt"
    install -m 0644 "${brand}/grub-background.png" "${root}/usr/share/grub/themes/vital/background.png"
    if [[ -f "${brand}/inter.pf2" ]]; then
        install -m 0644 "${brand}/inter.pf2" "${root}/usr/share/grub/themes/vital/inter.pf2"
    fi

    install -d "${root}/usr/share/vitalos/themes" \
        "${root}/etc/skel/.config/gtk-3.0" \
        "${root}/etc/skel/.config/gtk-4.0"
    install -m 0644 "${VITAL_ROOT_DIR}/branding/gtk/dark.css" "${root}/usr/share/vitalos/themes/dark.css"
    install -m 0644 "${VITAL_ROOT_DIR}/branding/gtk/light.css" "${root}/usr/share/vitalos/themes/light.css"
    filled="$(mktemp)"
    sed -e 's/__ACCENT__/#C6A56A/g' \
        -e 's/__ACCENT_HI__/#E4C992/g' \
        -e 's/__ACCENT_FG__/#14110C/g' \
        "${VITAL_ROOT_DIR}/branding/gtk/dark.css" > "$filled"
    install -m 0644 "$filled" "${root}/etc/skel/.config/gtk-3.0/gtk.css"
    install -m 0644 "$filled" "${root}/etc/skel/.config/gtk-4.0/gtk.css"
    rm -f "$filled"

    install -d "${root}/usr/share/vitalos/brand"
    install -m 0644 "${VITAL_ROOT_DIR}/branding/logo/vital-symbol.svg" "${root}/usr/share/vitalos/brand/vital-symbol.svg"
    install -m 0644 "${VITAL_ROOT_DIR}/branding/logo/vital-wordmark.svg" "${root}/usr/share/vitalos/brand/vital-wordmark.svg"
    install -m 0644 "${VITAL_ROOT_DIR}/branding/logo/vital-lockup.svg" "${root}/usr/share/vitalos/brand/vital-lockup.svg"
    install -d "${root}/usr/lib/vitalos" "${root}/usr/bin" "${root}/usr/libexec" \
        "${root}/usr/share/vitalos/marketplace" \
        "${root}/usr/share/icons/hicolor/scalable/apps"
    install -m 0755 "${VITAL_ROOT_DIR}/apps/vital-welcome/vital-welcome" "${root}/usr/bin/vital-welcome"
    install -m 0644 "${VITAL_ROOT_DIR}/apps/vital-welcome/identity.py" "${root}/usr/lib/vitalos/identity.py"
    install -m 0755 "${VITAL_ROOT_DIR}/apps/vital-marketplace/vital-marketplace" "${root}/usr/bin/vital-marketplace"
    install -m 0755 "${VITAL_ROOT_DIR}/apps/vital-marketplace/vital-marketplace-helper" "${root}/usr/libexec/vital-marketplace-helper"
    install -m 0755 "${VITAL_ROOT_DIR}/marketplace/cli/vital-market" "${root}/usr/bin/vital-market"
    install -m 0644 "${VITAL_ROOT_DIR}/marketplace/python/vital_catalog.py" "${root}/usr/lib/vitalos/vital_catalog.py"
    cp -a "${VITAL_ROOT_DIR}/marketplace/catalog/." "${root}/usr/share/vitalos/marketplace/"
    install -d "${root}/etc/vital"
    install -m 0644 "${VITAL_ROOT_DIR}/marketplace/keys/catalog.pub" "${root}/etc/vital/marketplace.pub"
    install -m 0644 "${VITAL_ROOT_DIR}/marketplace/keys/catalog.pub" "${root}/usr/share/vitalos/marketplace/catalog.pub"
    install -m 0755 "${VITAL_ROOT_DIR}/apps/vital-telemetry/vital-telemetry" "${root}/usr/bin/vital-telemetry"
    install -m 0755 "${VITAL_ROOT_DIR}/apps/vital-telemetry/vital-telemetry-ctl" "${root}/usr/bin/vital-telemetry-ctl"
    install -m 0644 "${VITAL_ROOT_DIR}/apps/vital-telemetry/vital_telemetry.py" "${root}/usr/lib/vitalos/vital_telemetry.py"
    install -m 0644 "${VITAL_ROOT_DIR}/PRIVACY.md" "${root}/usr/share/vitalos/PRIVACY.md"
    install -m 0644 "${VITAL_ROOT_DIR}/branding/logo/vital-market.svg" \
        "${root}/usr/share/icons/hicolor/scalable/apps/vitalos-market.svg"
    if [[ -f "${brand}/market-256.png" ]]; then
        install -m 0644 "${brand}/market-256.png" "${root}/usr/share/icons/hicolor/256x256/apps/vitalos-market.png"
    fi

    rm -rf "${root}/etc/calamares"
    install -d "${root}/etc/calamares/branding/vitalos"
    cp -a "${VITAL_ROOT_DIR}/config/calamares/modules" "${root}/etc/calamares/"
    install -m 0644 "${VITAL_ROOT_DIR}/config/calamares/settings.conf" "${root}/etc/calamares/settings.conf"
    cp -a "${VITAL_ROOT_DIR}/config/calamares/branding/vitalos/." "${root}/etc/calamares/branding/vitalos/"
    install -m 0644 "${brand}/symbol-256.png" "${root}/etc/calamares/branding/vitalos/logo.png"
    install -m 0644 "${brand}/symbol-128.png" "${root}/etc/calamares/branding/vitalos/icon.png"
    install -m 0644 "${brand}/lockup.png" "${root}/etc/calamares/branding/vitalos/welcome.png"
}

prepare_stage() {
    local stage="${ROOTFS}/tmp/vital-build"
    mkdir -p "$stage"
    cp "${VITAL_ROOT_DIR}/config/packages.desktop.list" "$stage/"
    cp "${VITAL_ROOT_DIR}/config/packages.live.list" "$stage/"
    cp "${VITAL_ROOT_DIR}/config/apt-preferences" "$stage/"
    cp "${CACHE}/packages.mozilla.org.asc" "$stage/"
    cp "${CACHE}/dash-to-dock.zip" "$stage/"
    cp "${CACHE}/papirus-folders" "$stage/"
    make_wallpaper_deb "${stage}/ubuntu-wallpapers.deb"
    write_identity_files "$stage"
    install -m 0755 "${VITAL_ROOT_DIR}/build/in-chroot/configure-system.sh" "${stage}/configure-system.sh"
    install -m 0644 "${VITAL_ROOT_DIR}/config/flathub.flatpakrepo" "${stage}/flathub.flatpakrepo"
    mkdir -p "${stage}/overlay"
    cp -a "${VITAL_ROOT_DIR}/overlay/." "${stage}/overlay/"
    chown -R root:root "${stage}/overlay"
}

build_squashfs() {
    local version kver manifest size squash
    version="$VERSION"
    mapfile -t kernels < <(find "${ROOTFS}/boot" -maxdepth 1 -type f -name 'vmlinuz-*' | sort -V)
    [[ "${#kernels[@]}" -gt 0 ]] || die "No kernel was installed into the rootfs"
    kver="$(basename "${kernels[-1]}")"
    kver="${kver#vmlinuz-}"
    mkdir -p "${ISO_TREE}/casper" "${ISO_TREE}/.disk"
    cp -a "${ROOTFS}/boot/vmlinuz-${kver}" "${ISO_TREE}/casper/vmlinuz"
    cp -a "${ROOTFS}/boot/initrd.img-${kver}" "${ISO_TREE}/casper/initrd"
    chmod 0644 "${ISO_TREE}/casper/vmlinuz" "${ISO_TREE}/casper/initrd"

    manifest="${ISO_TREE}/casper/filesystem.manifest"
    # dpkg-query expands ${Package} itself; the shell must not.
    # shellcheck disable=SC2016
    chroot "$ROOTFS" dpkg-query -W --showformat='${Package} ${Version}\n' > "$manifest"
    size="$(du -sx --block-size=1 "$ROOTFS" | cut -f1)"
    printf '%s\n' "$size" > "${ISO_TREE}/casper/filesystem.size"

    squash="${ISO_TREE}/casper/filesystem.squashfs"
    rm -f "$squash"
    local procs mem_mb
    procs="$(nproc)"
    mem_mb="$(awk '/MemAvailable:/ {print int($2/1024)}' /proc/meminfo)"
    if [[ "$mem_mb" -lt 8192 && "$procs" -gt 2 ]]; then
        procs=2
    fi
    log "Creating squashfs (${SQUASH_COMP}, ${procs} threads, ${mem_mb} MB available)"
    # Keep the mount-point directories. Casper and the installed system
    # need them present even when they are empty.
    if [[ "$SQUASH_COMP" == "xz" ]]; then
        mksquashfs "$ROOTFS" "$squash" -comp xz -Xbcj x86 -b 1M -processors "$procs" \
            -wildcards \
            -e 'proc/*' 'sys/*' 'dev/*' 'run/*' 'tmp/*' 'var/tmp/*' \
               'var/cache/apt/archives/*' 'var/lib/apt/lists/*' \
            -noappend
    else
        mksquashfs "$ROOTFS" "$squash" -comp "$SQUASH_COMP" -b 1M -processors "$procs" \
            -wildcards \
            -e 'proc/*' 'sys/*' 'dev/*' 'run/*' 'tmp/*' 'var/tmp/*' \
               'var/cache/apt/archives/*' 'var/lib/apt/lists/*' \
            -noappend
    fi
    printf '%s\n' "Vital OS ${version} \"Nocturne\" - Release amd64" > "${ISO_TREE}/.disk/info"
    printf '%s\n' "https://github.com/taltol15/vital-os/releases" > "${ISO_TREE}/.disk/release_notes_url"
    if [[ -r /proc/sys/kernel/random/uuid ]]; then
        cp /proc/sys/kernel/random/uuid "${ISO_TREE}/.disk/casper-uuid"
    fi
}

build_iso_tree() {
    local brand pc efi_dir efi_img
    brand="${WORK}/brand"
    mkdir -p "${ISO_TREE}/.disk" "${ISO_TREE}/boot/grub/i386-pc" \
        "${ISO_TREE}/boot/grub/themes/vital" "${ISO_TREE}/boot/grub/fonts"
    install -m 0644 "${VITAL_ROOT_DIR}/config/grub.cfg" "${ISO_TREE}/boot/grub/grub.cfg"
    install -m 0644 "${VITAL_ROOT_DIR}/branding/grub/theme.txt" "${ISO_TREE}/boot/grub/themes/vital/theme.txt"
    install -m 0644 "${brand}/grub-background.png" "${ISO_TREE}/boot/grub/themes/vital/background.png"
    [[ -f "${brand}/inter.pf2" ]] || die "GRUB font inter.pf2 was not generated (grub-mkfont and fonts-inter are required)"
    install -m 0644 "${brand}/inter.pf2" "${ISO_TREE}/boot/grub/fonts/inter.pf2"
    install -m 0644 "${brand}/inter.pf2" "${ISO_TREE}/boot/grub/themes/vital/inter.pf2"
    cp -a /usr/lib/grub/i386-pc/*.mod /usr/lib/grub/i386-pc/*.lst "${ISO_TREE}/boot/grub/i386-pc/"

    pc=/usr/lib/grub/i386-pc
    grub-mkimage -O i386-pc \
        -o "${ISO_TREE}/boot/grub/i386-pc/core.img" \
        -p /boot/grub \
        -d "$pc" \
        biosdisk iso9660 part_msdos part_gpt \
        search search_fs_file search_label \
        gfxterm gfxmenu png jpeg font \
        normal boot linux configfile \
        gzio all_video cat echo test true help ls loadenv
    cat "${pc}/cdboot.img" "${ISO_TREE}/boot/grub/i386-pc/core.img" > "${ISO_TREE}/boot/grub/i386-pc/eltorito.img"

    efi_dir="${WORK}/efi"
    rm -rf "$efi_dir"
    mkdir -p "$efi_dir"
    grub-mkstandalone -O x86_64-efi \
        -o "${efi_dir}/BOOTX64.EFI" \
        --modules="part_gpt part_msdos fat iso9660 search search_fs_file gfxterm gfxmenu png jpeg font normal boot linux configfile gzio all_video efi_gop efi_uga" \
        "boot/grub/grub.cfg=${ISO_TREE}/boot/grub/grub.cfg"
    efi_img="${ISO_TREE}/boot/grub/efi.img"
    rm -f "$efi_img"
    dd if=/dev/zero of="$efi_img" bs=1M count=32 status=none
    mkfs.vfat -n VITAL_EFI "$efi_img" >/dev/null
    mmd -i "$efi_img" ::/EFI ::/EFI/BOOT
    mcopy -i "$efi_img" "${efi_dir}/BOOTX64.EFI" ::/EFI/BOOT/BOOTX64.EFI
    mkdir -p "${ISO_TREE}/EFI/BOOT"
    install -m 0644 "${efi_dir}/BOOTX64.EFI" "${ISO_TREE}/EFI/BOOT/BOOTX64.EFI"

    local sums
    sums="$(mktemp)"
    (
        cd "$ISO_TREE"
        find . -type f -print0 | sort -z | xargs -0 md5sum > "$sums"
    )
    mv "$sums" "${ISO_TREE}/md5sum.txt"
}

wrap_iso() {
    local outfile
    mkdir -p "$OUTPUT"
    outfile="${OUTPUT}/VitalOS-${VERSION}-amd64.iso"
    rm -f "$outfile"
    log "Writing ${outfile}"
    xorriso -as mkisofs \
        -r -V "VITALOS" \
        -o "$outfile" \
        -J -joliet-long \
        -iso-level 3 \
        -eltorito-boot boot/grub/i386-pc/eltorito.img \
        -no-emul-boot \
        -boot-load-size 4 \
        -boot-info-table \
        --grub2-boot-info \
        -eltorito-catalog boot/grub/boot.cat \
        -eltorito-alt-boot \
        -e boot/grub/efi.img \
        -no-emul-boot \
        -append_partition 2 0xef "${ISO_TREE}/boot/grub/efi.img" \
        -appended_part_as_gpt \
        -isohybrid-gpt-basdat \
        "$ISO_TREE"
    log "ISO ready: ${outfile}"
    ls -lh "$outfile"
}

build_iso() {
    [[ "$(id -u)" -eq 0 ]] || die "The ISO build needs root (debootstrap and mounts)."
    trap cleanup EXIT
    ensure_host_deps
    mkdir -p "$WORK" "$OUTPUT" "$CACHE"
    ensure_space_and_swap
    stage_downloads

    if [[ ! -d "${ROOTFS}/etc" ]]; then
        log "Bootstrapping Ubuntu noble into ${ROOTFS}"
        mkdir -p "$ROOTFS"
        debootstrap --arch=amd64 --variant=minbase noble "$ROOTFS" "$MIRROR"
    else
        log "Reusing existing rootfs at ${ROOTFS}"
    fi

    mount_chroot "$ROOTFS"
    MOUNTED=1
    log "Copying overlay and branding"
    rsync -a --chown=root:root "${VITAL_ROOT_DIR}/overlay/" "${ROOTFS}/"
    python3 "${VITAL_ROOT_DIR}/tools/render_previews.py" --export "${WORK}/brand" --skip-docs
    install_brand_assets "$ROOTFS" "${WORK}/brand"
    prepare_stage
    log "Installing packages inside the chroot. This is the long step."
    # Drop the host sudo identity. Tools such as papirus-folders treat
    # SUDO_USER as a user inside the rootfs and abort when that account
    # does not exist there.
    chroot "$ROOTFS" /usr/bin/env -u SUDO_USER -u SUDO_UID -u SUDO_GID -u PKEXEC_UID \
        /bin/bash /tmp/vital-build/configure-system.sh
    umount_chroot "$ROOTFS"
    MOUNTED=0

    rm -rf "$ISO_TREE"
    mkdir -p "$ISO_TREE"
    build_squashfs
    build_iso_tree
    wrap_iso
    if [[ "${VITAL_KEEP_ROOTFS:-0}" != "1" ]]; then
        log "Removing the rootfs to free disk. Set VITAL_KEEP_ROOTFS=1 to keep it."
        rm -rf "$ROOTFS"
    fi
}

usage() {
    cat <<EOF
Usage: ./build.sh <command>

  check          Shellcheck, syntax, and layout checks. No root.
  screenshots    Render docs/screenshots from the SVG branding.
  install-deps   apt-get the host packages used to build the ISO.
  iso            Build the hybrid BIOS/UEFI live ISO (root).
  clean          Delete build/work and build/output (root if files are root-owned).

Environment:
  VITAL_MIRROR           Debian-style mirror (default: Ubuntu archive)
  VITAL_SQUASHFS_COMP    xz (default) or gzip
  VITAL_KEEP_ROOTFS=1    Keep the debootstrap tree after a successful ISO
EOF
}

main() {
    local cmd="${1:-iso}"
    case "$cmd" in
        check)
            bash "${VITAL_ROOT_DIR}/build/check.sh"
            ;;
        screenshots)
            python3 "${VITAL_ROOT_DIR}/tools/render_previews.py" --export "${WORK}/brand"
            ;;
        install-deps)
            install_host_deps
            ;;
        iso)
            build_iso
            ;;
        clean)
            [[ "$(id -u)" -eq 0 ]] || die "clean needs root because the rootfs is owned by root"
            umount_chroot "$ROOTFS" || true
            rm -rf "$WORK" "$OUTPUT"
            ;;
        -h|--help|help)
            usage
            ;;
        *)
            usage >&2
            die "Unknown command: ${cmd}"
            ;;
    esac
}

main "$@"
