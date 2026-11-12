#!/bin/sh
# Install the pinned llama.cpp runtime and the official Qwen3 0.6B Q8 GGUF.
# Marketplace shows this script before it runs. Checksums are the review.
# CPU is always installed. Vulkan is added only when a GPU render node exists.
# Nothing here is executed from the archive except the llama-server binary
# the assistant starts later. Shared libraries are copied beside it.
set -eu

CPU_URL="https://github.com/ggml-org/llama.cpp/releases/download/b12212/llama-b12212-bin-ubuntu-x64.tar.gz"
CPU_SHA="a9b987738e6724b116980de8f5e15a901a3086587c3d2328533d77582e25ad5b"
VULKAN_URL="https://github.com/ggml-org/llama.cpp/releases/download/b12212/llama-b12212-bin-ubuntu-vulkan-x64.tar.gz"
VULKAN_SHA="1f4c94a3a38b52ed632924aba9cdfa736caaa3ea7812b62ca1d8b84917eb3e15"
MODEL_URL="https://huggingface.co/Qwen/Qwen3-0.6B-GGUF/resolve/main/Qwen3-0.6B-Q8_0.gguf"
MODEL_SHA="9465e63a22add5354d9bb4b99e90117043c7124007664907259bd16d043bb031"
MODEL_NAME="Qwen3-0.6B-Q8_0.gguf"

PREFIX="${VITAL_LLAMA_PREFIX:-/usr/lib/vitalos/llama}"
MODEL_DIR="${VITAL_LOCAL_MODEL_DIR:-/var/lib/vitalos/models}"

if [ "${VITAL_LOCAL_MODEL_DRY_RUN:-}" = "1" ]; then
    printf 'cpu %s\n' "$CPU_SHA"
    printf 'vulkan %s\n' "$VULKAN_SHA"
    printf 'model %s\n' "$MODEL_SHA"
    printf 'model_name %s\n' "$MODEL_NAME"
    printf 'license model Apache-2.0 llama.cpp MIT\n'
    exit 0
fi

if [ "$(id -u)" -ne 0 ]; then
    case "$PREFIX" in
        /usr/*|/var/*|/opt/*)
            echo "Refusing to install into ${PREFIX} without root." >&2
            exit 1
            ;;
    esac
fi

fetch() {
    url=$1
    dest=$2
    want=$3
    echo "Downloading ${url}"
    curl -fsSL --retry 3 --retry-delay 2 -o "${dest}.partial" "$url"
    got=$(sha256sum "${dest}.partial" | awk 'NR==1 { print $1 }')
    if [ "$got" != "$want" ]; then
        echo "Checksum mismatch for ${dest}: got ${got}" >&2
        rm -f "${dest}.partial"
        exit 1
    fi
    mv "${dest}.partial" "$dest"
}

extract_runtime() {
    tarball=$1
    dest=$2
    rm -rf "$dest"
    mkdir -p "$dest"
    python3 - "$tarball" "$dest" <<'PY'
import sys
import tarfile
from pathlib import Path

archive = Path(sys.argv[1])
dest = Path(sys.argv[2])
with tarfile.open(archive) as tar:
    for member in tar.getmembers():
        parts = Path(member.name).parts
        if not parts or member.name.startswith("/") or ".." in parts:
            raise SystemExit(f"refusing archive member {member.name}")
    tar.extractall(dest, filter="data")
server = list(dest.rglob("llama-server"))
if len(server) != 1 or not server[0].is_file():
    raise SystemExit("llama-server was not found after extract")
server[0].chmod(0o755)
PY
}

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

mkdir -p "$PREFIX" "$MODEL_DIR"
fetch "$CPU_URL" "$work/cpu.tar.gz" "$CPU_SHA"
extract_runtime "$work/cpu.tar.gz" "$PREFIX/cpu"

if [ -e /dev/dri/renderD128 ]; then
    fetch "$VULKAN_URL" "$work/vulkan.tar.gz" "$VULKAN_SHA"
    extract_runtime "$work/vulkan.tar.gz" "$PREFIX/vulkan"
fi

fetch "$MODEL_URL" "$MODEL_DIR/$MODEL_NAME.partial" "$MODEL_SHA"
mv "$MODEL_DIR/$MODEL_NAME.partial" "$MODEL_DIR/$MODEL_NAME"
chmod 644 "$MODEL_DIR/$MODEL_NAME"

cpu_bin=$(find "$PREFIX/cpu" -type f -name llama-server | awk 'NR==1 { print; exit }')
vulkan_bin=""
if [ -d "$PREFIX/vulkan" ]; then
    vulkan_bin=$(find "$PREFIX/vulkan" -type f -name llama-server | awk 'NR==1 { print; exit }')
fi

python3 - "$PREFIX/manifest.json" "$cpu_bin" "$vulkan_bin" "$MODEL_DIR/$MODEL_NAME" <<'PY'
import json
import sys
from pathlib import Path

path, cpu, vulkan, model = sys.argv[1:]
Path(path).write_text(
    json.dumps(
        {
            "cpu_binary": cpu,
            "vulkan_binary": vulkan,
            "model": model,
            "llama_cpp": "b12212",
            "model_sha256": "9465e63a22add5354d9bb4b99e90117043c7124007664907259bd16d043bb031",
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
PY
chmod 644 "$PREFIX/manifest.json"
echo "Installed ${MODEL_NAME} and llama.cpp b12212 under ${PREFIX}"
