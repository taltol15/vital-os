#!/usr/bin/env bash
# Runs inside the debootstrap chroot. Expects /tmp/vital-build to hold
# package lists, pins, the Mozilla key, Dash to Dock, and identity files.
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

STAGE=/tmp/vital-build

log() {
    printf '[vital-chroot] %s\n' "$*"
}

die() {
    printf '[vital-chroot] %s\n' "$*" >&2
    exit 1
}

log "Configuring apt sources"
install -d -m 0755 /etc/apt/keyrings /etc/apt/preferences.d /etc/apt/apt.conf.d /etc/apt/sources.list.d
cat > /etc/apt/sources.list <<'EOF'
deb http://archive.ubuntu.com/ubuntu noble main restricted universe multiverse
deb http://archive.ubuntu.com/ubuntu noble-updates main restricted universe multiverse
deb http://security.ubuntu.com/ubuntu noble-security main restricted universe multiverse
deb http://archive.ubuntu.com/ubuntu noble-backports main restricted universe multiverse
EOF
install -m 0644 "${STAGE}/apt-preferences" /etc/apt/preferences.d/vitalos
cat > /etc/apt/apt.conf.d/99vital-norecommends-snap <<'EOF'
APT::Get::Assume-Yes "true";
Dpkg::Options { "--force-confdef"; "--force-confold"; };
EOF

ln -sfn /usr/share/zoneinfo/UTC /etc/localtime
printf 'UTC\n' > /etc/timezone

log "Satisfying gnome-shell's ubuntu-wallpapers dependency without the artwork"
dpkg -i "${STAGE}/ubuntu-wallpapers.deb"

apt-get update
apt-get install -y eatmydata

mapfile -t desktop_packages < <(grep -E '^[[:alnum:]][[:alnum:].+-]*$' "${STAGE}/packages.desktop.list")
mapfile -t live_packages < <(grep -E '^[[:alnum:]][[:alnum:].+-]*$' "${STAGE}/packages.live.list")
((${#desktop_packages[@]} > 0)) || die "Desktop package list is empty"
((${#live_packages[@]} > 0)) || die "Live package list is empty"

log "Installing the desktop package set (${#desktop_packages[@]} packages)"
eatmydata apt-get install -y "${desktop_packages[@]}"
log "Installing live-session packages"
eatmydata apt-get install -y "${live_packages[@]}"

log "Installing Firefox from packages.mozilla.org"
install -m 0644 "${STAGE}/packages.mozilla.org.asc" /etc/apt/keyrings/packages.mozilla.org.asc
printf 'deb [signed-by=/etc/apt/keyrings/packages.mozilla.org.asc] https://packages.mozilla.org/apt mozilla main\n' \
    > /etc/apt/sources.list.d/mozilla.list
apt-get update
eatmydata apt-get install -y firefox

log "Installing Dash to Dock"
dock_dir=/usr/share/gnome-shell/extensions/dash-to-dock@micxgx.gmail.com
rm -rf "$dock_dir"
mkdir -p "$dock_dir"
unzip -q "${STAGE}/dash-to-dock.zip" -d "$dock_dir"
schema_src="${dock_dir}/schemas/org.gnome.shell.extensions.dash-to-dock.gschema.xml"
[[ -f "$schema_src" ]] || die "Dash to Dock schema missing from the archive"
install -m 0644 "$schema_src" /usr/share/glib-2.0/schemas/org.gnome.shell.extensions.dash-to-dock.gschema.xml
glib-compile-schemas /usr/share/glib-2.0/schemas

if [[ -x "${STAGE}/papirus-folders" ]]; then
    install -m 0755 "${STAGE}/papirus-folders" /usr/local/sbin/papirus-folders
    if env -u SUDO_USER -u SUDO_UID -u SUDO_GID -u PKEXEC_UID \
        /usr/local/sbin/papirus-folders -t Papirus-Dark -l | grep -q 'palebrown'; then
        log "Tinting Papirus-Dark folders palebrown"
        env -u SUDO_USER -u SUDO_UID -u SUDO_GID -u PKEXEC_UID \
            /usr/local/sbin/papirus-folders -t Papirus-Dark -C palebrown
    else
        log "palebrown folders were not in this Papirus build; leaving the default tint"
    fi
fi

log "Generating locales"
sed -i 's/^# *\(en_US.UTF-8 UTF-8\)/\1/' /etc/locale.gen
locale-gen en_US.UTF-8
update-locale LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8

if [[ -L /etc/os-release ]]; then
    install -m 0644 "${STAGE}/os-release" /usr/lib/os-release
else
    install -m 0644 "${STAGE}/os-release" /etc/os-release
    install -m 0644 "${STAGE}/os-release" /usr/lib/os-release
fi
install -m 0644 "${STAGE}/lsb-release" /etc/lsb-release

if [[ -f /etc/default/whoopsie ]]; then
    if grep -q '^report_crashes=' /etc/default/whoopsie; then
        sed -i 's/^report_crashes=.*/report_crashes=false/' /etc/default/whoopsie
    else
        printf 'report_crashes=false\n' >> /etc/default/whoopsie
    fi
fi
mkdir -p /etc/systemd/system
ln -sfn /dev/null /etc/systemd/system/whoopsie.service
ln -sfn /dev/null /etc/systemd/system/whoopsie.path

log "Restoring Vital OS files that package scripts may have replaced"
cp -a "${STAGE}/overlay/." /
install -d -m 0755 /etc/flatpak/remotes.d
install -m 0644 "${STAGE}/flathub.flatpakrepo" /etc/flatpak/remotes.d/flathub.flatpakrepo

log "Compiling dconf defaults"
dconf update

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f /usr/share/icons/hicolor || true
    if [[ -d /usr/share/icons/Papirus-Dark ]]; then
        gtk-update-icon-cache -f /usr/share/icons/Papirus-Dark || true
    fi
fi

log "Setting the Plymouth theme and rebuilding the initramfs"
# Ubuntu 24.04 selects the splash through the default.plymouth alternative.
# plymouth-set-default-theme is not shipped in this plymouth package.
update-alternatives --install /usr/share/plymouth/themes/default.plymouth default.plymouth \
    /usr/share/plymouth/themes/vitalos/vitalos.plymouth 200
update-alternatives --set default.plymouth /usr/share/plymouth/themes/vitalos/vitalos.plymouth
if command -v plymouth-set-default-theme >/dev/null 2>&1; then
    plymouth-set-default-theme vitalos
fi
update-initramfs -u -k all

log "Cleaning the rootfs"
apt-get clean
rm -rf /var/lib/apt/lists/*
mkdir -p /var/lib/apt/lists/partial
rm -rf /tmp/* /var/tmp/*
find /var/log -type f -delete || true
: > /etc/machine-id
rm -f /var/lib/dbus/machine-id
ln -sfn /etc/machine-id /var/lib/dbus/machine-id
rm -f /etc/resolv.conf
ln -sfn ../run/systemd/resolve/stub-resolv.conf /etc/resolv.conf

log "Chroot configuration finished"
