#!/bin/bash
# Explicit per-kernel build only. No installation hooks, DKMS registration or GRUB edits.
set -euo pipefail
LIB=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
[[ $# == 2 ]] || { echo "Usage: $0 KERNEL ASSET_DIRECTORY" >&2; exit 2; }
K=$1 ASSETS=$(realpath -- "$2")
[[ $EUID == 0 ]] || { echo 'Requires root to build an initramfs, NOT permission to load the module.' >&2; exit 1; }
[[ $K =~ ^[A-Za-z0-9._+-]+$ ]] || exit 1
exec 9>/run/lock/server3090-image.lock
flock -n 9 || exit 1
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 22.04 ]] || { echo 'Only Ubuntu 22.04 is in scope.' >&2; exit 1; }
[[ -d /lib/modules/$K/build && -f /boot/vmlinuz-$K && -f /boot/initrd.img-$K ]] || exit 1
for tool in mkinitramfs unmkinitramfs modinfo depmod make gcc python3 sha256sum; do command -v "$tool" >/dev/null; done
# A normal image must remain stock even on future kernel updates.
[[ ! -e /usr/share/initramfs-tools/modules.d/gpu-unlock.conf ]] || { echo 'Upstream initramfs integration already installed; refuse mixed ownership.' >&2; exit 1; }
if find /lib/modules -name 'gpu_unlock.ko*' -print -quit | grep -q .; then echo 'Existing global gpu_unlock installation; refuse.' >&2; exit 1; fi
# A built-in binder cannot be removed from the image.
(cd "$LIB"; python3 - "$K" <<'PY_CHECK'
import sys
from pathlib import Path
from common import BINDER
p = Path('/lib/modules') / sys.argv[1] / 'modules.builtin'
if not p.is_file():
    raise SystemExit('Missing modules.builtin')
for name in p.read_text().splitlines():
    if BINDER.fullmatch(Path(name).name) and Path(name).name not in ("vfio-pci.ko", "vfio-pci-core.ko"):
        raise SystemExit('Built-in GPU binder not supported: ' + name)
PY_CHECK
)
if [[ -r /sys/kernel/security/lockdown ]] && ! grep -q '\[none\]' /sys/kernel/security/lockdown; then
 echo 'Kernel lockdown/signing configuration unsupported by this builder.' >&2; exit 1
fi
ROOT=$(cd "$LIB/../.." && pwd)
WORK=$(mktemp -d /var/tmp/server3090.XXXXXX)
STAGED=''
trap 'rc=$?; rm -rf -- "$WORK"; [[ -z $STAGED ]] || rm -f -- "$STAGED"; exit "$rc"' EXIT
mkdir -p "$WORK/lib/assets" "$WORK/src" "$WORK/audit"
cp "$LIB"/{gate,image-hook,audit.py,common.py} "$WORK/lib/"
cp "$ROOT/firmware/artifacts-610.43.03.json" "$WORK/lib/artifacts.json"
cp "$ASSETS"/*.bin "$WORK/lib/assets/"
(cd "$WORK/lib"; python3 -c 'from common import verify_assets; verify_assets("assets", "artifacts.json")')
cp "$ROOT/kernel/gpu_unlock/"*.[ch] "$ROOT/kernel/gpu_unlock/"{Makefile,Kbuild} "$WORK/src/"
make -C "$WORK/src" KDIR="/lib/modules/$K/build"
[[ $(modinfo -F vermagic "$WORK/src/gpu_unlock.ko") == "$K "* ]] || exit 1
cp -a /etc/initramfs-tools "$WORK/config"
mkdir -p "$WORK/config/hooks" "$WORK/config/scripts/init-top"
install -m755 "$WORK/lib/gate" "$WORK/config/scripts/init-top/00-server3090"
install -m755 "$WORK/lib/image-hook" "$WORK/config/hooks/zzzz-server3090"
# Fingerprint every existing boot image, not just the chosen kernel.
find /boot -maxdepth 1 -type f \( -name 'initrd.img-*' -o -name 'vmlinuz-*' \) -exec sha256sum {} + > "$WORK/stock.sha256"
export SERVER3090_KERNEL="$K"
export SERVER3090_LIB="$WORK/lib" SERVER3090_MODULE="$WORK/src/gpu_unlock.ko"
mkinitramfs -d "$WORK/config" -o "$WORK/image" "$K"
unmkinitramfs "$WORK/image" "$WORK/audit"
python3 "$WORK/lib/audit.py" --root "$WORK/audit" --kernel "$K" --module "$SERVER3090_MODULE" --lib "$WORK/lib"  > "$WORK/audit.json"
sha256sum -c "$WORK/stock.sha256"
OUT="/boot/initrd.img-$K-server3090"
[[ ! -L $OUT && ( ! -e $OUT || -f $OUT ) ]] || exit 1
STAGED=$(mktemp "/boot/.server3090.XXXXXX")
install -m600 "$WORK/image" "$STAGED"
cmp "$WORK/image" "$STAGED"
sync -f "$STAGED"
mv -f -- "$STAGED" "$OUT"; STAGED=''
LOG="/var/log/gpu-unlock-server3090/$K"
mkdir -p "$LOG"
cp "$WORK/audit.json" "$WORK/stock.sha256" "$LOG/"
sha256sum "$OUT" > "$LOG/image.sha256"
printf 'Built %s. No GRUB changes, global module installation, loading or reboot.\n' "$OUT"
