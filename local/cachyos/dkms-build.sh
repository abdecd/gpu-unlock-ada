#!/bin/bash
set -euo pipefail
kdir=${1:?kernel build directory required}
[[ -f "$kdir/.config" ]] || { echo "Missing kernel config: $kdir/.config" >&2; exit 1; }
if grep -qx 'CONFIG_CC_IS_CLANG=y' "$kdir/.config"; then
    exec make KDIR="$kdir" LLVM=1
else
    exec make KDIR="$kdir" LLVM=
fi
