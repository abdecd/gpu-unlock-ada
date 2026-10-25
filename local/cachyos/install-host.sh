#!/bin/bash
# Register/build DKMS and pinned firmware. Does not load/reload, rebuild initramfs,
# change GRUB defaults, or reboot. Run only from local/cachyos-dkms checkout.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
ASSETS=${1:?Usage: install-host.sh /absolute/path/to/verified/assets}
NAME=gpu-unlock-4060-local
VER=1.1.1.ad107.1
SRC="/usr/src/$NAME-$VER"
FW=/usr/lib/firmware/gpu-unlock/610.43.03
CONF=/etc/dracut.conf.d/zz-gpu-unlock-local-stock-omit.conf
[[ $EUID == 0 && $ASSETS == /* ]] || exit 1
[[ ! -e $SRC && ! -L $SRC && ! -e $FW && ! -L $FW && ! -e $CONF && ! -L $CONF ]] || { echo 'Existing local install paths; refusing overwrite.' >&2; exit 1; }
command -v dkms >/dev/null; command -v clang >/dev/null
python3 "$ROOT/local/cachyos/verify-assets.py" "$ASSETS"
# Avoid relying on working copy at runtime, including /run/media availability.
install -d "$SRC" "$FW"
install -m644 "$ROOT"/kernel/gpu_unlock/*.[ch] "$ROOT/kernel/gpu_unlock/Makefile" "$ROOT/kernel/gpu_unlock/Kbuild" "$SRC/"
install -m644 "$ROOT/local/cachyos/dkms.conf" "$SRC/dkms.conf"
install -d "$SRC/local"
install -m644 "$ROOT/local/cachyos/dkms-build.sh" "$SRC/local/dkms-build.sh"
for f in "$ASSETS/"*.bin; do install -m644 "$f" "$FW/"; done
install -m644 "$ASSETS/NVIDIA-LICENSE" "$FW/NVIDIA-LICENSE"
# Do not let ordinary hostonly stock dracut images capture the loaded out-of-tree
# module. Dedicated image rebuilds explicitly bypass this host confdir.
printf '%s\n' '# Local AD107: ordinary boot images must remain unlock-free.' 'omit_drivers+=" gpu_unlock "' > "$CONF"
dkms add -m "$NAME" -v "$VER"
failed=0
for path in /usr/lib/modules/*/build; do
 [[ -e "$path" ]] || continue
 k=${path%/build};k=${k##*/}
 if ! dkms build -m "$NAME" -v "$VER" -k "$k"; then failed=1; continue; fi
 if ! dkms install -m "$NAME" -v "$VER" -k "$k"; then failed=1; fi
done
dkms status -m "$NAME" -v "$VER"
if ((failed)); then echo 'One or more kernels failed. Inspect DKMS logs; no boot image was changed.' >&2; exit 1; fi
echo 'DKMS installed; no modprobe/reload/initramfs/GRUB/reboot performed.'
echo 'Existing TEST image is unchanged and still contains its previously tested module.'
