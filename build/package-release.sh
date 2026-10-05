#!/usr/bin/env bash
# Split a built ISO into GitHub-sized parts and write SHA256SUMS.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(tr -d '[:space:]' < "${ROOT}/VERSION")"
OUTPUT="${ROOT}/build/output"
RELEASE="${OUTPUT}/release"
# Stay under GitHub's 2 GiB asset limit.
PART_BYTES=$((1900 * 1024 * 1024))

shopt -s nullglob
isos=("${OUTPUT}/VitalOS-${VERSION}-amd64.iso")
if [[ ! -f "${isos[0]}" ]]; then
    printf 'No ISO at %s\n' "${isos[0]}" >&2
    exit 1
fi

rm -rf "$RELEASE"
mkdir -p "$RELEASE"
iso="${isos[0]}"
size="$(stat -c '%s' "$iso")"
base="$(basename "$iso")"

if [[ "$size" -gt "$PART_BYTES" ]]; then
    split -b "$PART_BYTES" -d -a 2 "$iso" "${RELEASE}/${base}.part"
else
    cp -a "$iso" "${RELEASE}/${base}"
fi

cat > "${RELEASE}/README-download.txt" <<EOF
Vital OS ${VERSION} amd64 live/install ISO

If the image was split, join the parts before writing it to a USB drive
or attaching it to a virtual machine:

  cat ${base}.part* > ${base}
  sha256sum -c SHA256SUMS

A single-file upload uses the name ${base} and the same checksum file.
The ISO is a hybrid BIOS and UEFI image. Secure Boot is not supported
in this release; turn it off to boot.
EOF

(
    cd "$RELEASE"
    sha256sum ./* > SHA256SUMS
)
printf 'Release files:\n'
ls -lh "$RELEASE"
