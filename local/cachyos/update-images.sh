#!/bin/bash
# Build per-pkgbase unlock images only. NEVER writes GRUB or stock initramfs.
set -euo pipefail
LIB=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
[[ $EUID == 0 ]] || { echo 'Requires root host.' >&2; exit 1; }
exec 9>/run/lock/gpu-unlock-4060-update.lock
flock -n 9 || { echo 'Another unlock image update running.' >&2; exit 1; }
[[ -d /boot && ! -L /boot ]] || exit 1
mkdir -p /var/log/gpu-unlock-4060
LOG=/var/log/gpu-unlock-4060
WORK=''; STAGED=''
cleanup() {
 rc=$?; trap - EXIT
 [[ -z $WORK || ! -d $WORK ]] || rm -rf -- "$WORK"
 [[ -z $STAGED || ! -e $STAGED ]] || rm -f -- "$STAGED"
 exit "$rc"
}
trap cleanup EXIT
# Refuse ambiguous package names before publishing any image.
declare -A seen=()
dirs=()
for dir in /usr/lib/modules/*; do
 [[ -f $dir/pkgbase && -f $dir/vmlinuz ]] || continue
 k=${dir##*/}; pkg=$(cat "$dir/pkgbase")
 [[ $k =~ ^[A-Za-z0-9._+-]+$ && $pkg =~ ^linux([A-Za-z0-9._+-]*)$ ]] || { echo "Unsafe kernel identity: $dir" >&2; exit 1; }
 [[ ! ${seen[$pkg]+yes} ]] || { echo "Duplicate installed pkgbase $pkg: refusing ambiguous image name." >&2; exit 1; }
 seen[$pkg]=$k
 dirs+=("$dir")
done
count=0; failed=0
build_one() (
 set -euo pipefail
 dir=$1; k=${dir##*/};pkg=$(cat "$dir/pkgbase")
 [[ -f $dir/build/.config ]] || { echo "SKIP/ERROR $k: missing headers" >&2; exit 1; }
 dkms status -m gpu-unlock-4060-local -v 1.1.1.ad107.1 -k "$k" | grep -q ': installed' || { echo "ERROR $k: DKMS not installed" >&2; exit 1; }
 mod=$(modinfo -k "$k" -n gpu_unlock)
 [[ $mod == */updates/dkms/gpu_unlock.ko* ]] || exit 1
 [[ $(modinfo -k "$k" -F vermagic gpu_unlock) == "$k "* ]] || exit 1
 modinfo -k "$k" -p gpu_unlock | grep -q '^ad107_result:' || exit 1
 out="/boot/initramfs-$pkg-unlock.img"
 [[ ! -L $out && ( ! -e $out || -f $out ) ]] || { echo 'Unsafe output path' >&2; exit 1; }
 WORK=$(mktemp -d /var/tmp/gpu-unlock-dkms.XXXXXX)
 STAGED=''
 trap 'rc=$?; rm -rf -- "$WORK"; [[ -z $STAGED || ! -e $STAGED ]] || rm -f -- "$STAGED"; exit "$rc"' EXIT
 mkdir "$WORK/conf" "$WORK/audit"
 # Hash original system images before/after; never write them.
 stock=("/boot/initramfs-$pkg.img" "/boot/initramfs-$pkg-fallback.img")
 : > "$WORK/stock.sha256"
 for f in "${stock[@]}"; do [[ ! -f $f ]] || sha256sum "$f" >> "$WORK/stock.sha256"; done
 case "$mod" in
 *.zst) zstd -qdc "$mod" > "$WORK/expected.ko";;
 *.xz) xz -dc "$mod" > "$WORK/expected.ko";;
 *.gz) gzip -dc "$mod" > "$WORK/expected.ko";;
 *.ko) cp "$mod" "$WORK/expected.ko";;
 *) exit 1;; esac
 dracut --conf /dev/null --confdir "$WORK/conf" --compress zstd --nostrip \
  --no-hostonly-cmdline --no-uefi --add systemd --add-drivers gpu_unlock \
  --omit-drivers 'nvidia nvidia_drm nvidia_modeset nvidia_uvm nvidia_peermem nouveau vfio_pci vfio_pci_core pci_stub xen_pciback pciback uio_pci_generic' \
  --install "$(command -v modprobe) $(command -v mkdir) /bin/sh" \
  --include "$LIB/image-overlay" / "$WORK/initramfs.img" "$k" > "$LOG/build-$k.log" 2>&1
 (cd "$WORK/audit"; lsinitrd --unpack "$WORK/initramfs.img")
 python3 "$LIB/verify-installed-image.py" "$WORK/audit" --kernel "$k" --module "$WORK/expected.ko" \
  --assets /usr/lib/firmware/gpu-unlock/610.43.03 --overlay "$LIB/image-overlay" > "$LOG/audit-$k.json"
 [[ ! -s $WORK/stock.sha256 ]] || sha256sum -c "$WORK/stock.sha256"
 # Copy on /boot's filesystem and rename only after image audit passes.
 STAGED=$(mktemp "/boot/.initramfs-$pkg-unlock.XXXXXX")
 install -m600 "$WORK/initramfs.img" "$STAGED"
 cmp "$WORK/initramfs.img" "$STAGED"
 sync -f "$STAGED"
 mv -f -- "$STAGED" "$out";STAGED=''
 sha256sum "$out" > "$LOG/$pkg-unlock.sha256"
 printf '%s\n' "$k" > "$LOG/$pkg-unlock.kernel"
 echo "Published $out (kernel $k); ordinary/fallback images unchanged."
)
# Do not call a build function as an if condition: it disables errexit inside it.
for dir in "${dirs[@]}"; do
 set +e
 build_one "$dir"
 rc=$?
 set -e
 if ((rc)); then echo "FAILED ${dir##*/}: previous unlock image retained; do not boot it with a new unmatched kernel." >&2; failed=$((failed+1)); else count=$((count+1)); fi
done
printf 'Unlock images: %s successful, %s failed. No GRUB/default/kernel-copy changes or reboot.\n' "$count" "$failed"
((count>0 && failed==0))
