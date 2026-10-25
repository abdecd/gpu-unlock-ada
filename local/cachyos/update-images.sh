#!/bin/bash
# Root-owned installed helper. Build/audit/publish independent images only.
set -euo pipefail
LIB=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
[[ $EUID == 0 ]] || { echo 'Requires root host.' >&2; exit 1; }
CONF=/etc/gpu-unlock-4060.conf
[[ -f $CONF && ! -L $CONF && $(stat -c %u "$CONF") == 0 ]] || exit 1
# Admin-owned host-specific settings. Not sourced from removable working repo.
[[ $((8#$(stat -c %a "$CONF") & 8#022)) == 0 ]] || { echo 'Config writable by non-root.' >&2; exit 1; }
source "$CONF"
[[ ${KERNEL_PKGBASE:-} == linux-cachyos && ${TARGET_BDF:-} == 0000:01:00.0 ]] || exit 1
[[ $(findmnt -n -o TARGET -T /boot) == / && $(findmnt -n -o FSTYPE -T /boot) == ext4 ]] || { echo 'Separate /boot unsupported by this host-specific GRUB generator.' >&2; exit 1; }
[[ $ROOT_UUID =~ ^[a-fA-F0-9-]+$ && $LINUX_CMDLINE != *gpu_unlock* && $LINUX_CMDLINE != *\'* && $LINUX_CMDLINE != *\$* && $LINUX_CMDLINE != *\`* && $LINUX_CMDLINE != *$'\n'* ]] || { echo 'Unsafe host cmdline.' >&2; exit 1; }
for token in $LINUX_CMDLINE; do
 [[ $token =~ ^[A-Za-z0-9_.,:=/@+%-]+$ && $token != gpu-unlock.* ]] || { echo 'Unsafe cmdline token.' >&2; exit 1; }
done
[[ " $LINUX_CMDLINE " == *" root=UUID=$ROOT_UUID "* ]] || { echo 'Root UUID mismatch.' >&2; exit 1; }
exec 9>/run/lock/gpu-unlock-4060-update.lock
flock -n 9 || { echo 'Another update running.' >&2; exit 1; }
mkdir -p /boot/gpu-unlock-4060 /var/log/gpu-unlock-4060
LOG=/var/log/gpu-unlock-4060
MENU=$(mktemp /boot/grub/.gpu-unlock-menu.XXXXXX)
WORK=''
cleanup(){ rc=$?; trap - EXIT; [[ -z $WORK || ! -d $WORK ]] || rm -rf -- "$WORK"; [[ ! -e $MENU ]] || rm -f -- "$MENU"; exit "$rc"; }
trap cleanup EXIT
printf '%s\n' '# Managed by gpu-unlock-4060-local. Manual-only entries; stock default unchanged.' > "$MENU"
count=0
for dir in /usr/lib/modules/*; do
 [[ -f $dir/pkgbase && -f $dir/vmlinuz && -f $dir/build/.config ]] || continue
 [[ $(cat "$dir/pkgbase") == "$KERNEL_PKGBASE" ]] || continue
 k=${dir##*/}
 [[ $k =~ ^[A-Za-z0-9._+-]+$ ]] || exit 1
 dkms status -m gpu-unlock-4060-local -v 1.1.1.ad107.1 -k "$k" | grep -q ': installed' || { echo "DKMS unavailable for $k; retaining prior menu." >&2; exit 1; }
 mod=$(modinfo -k "$k" -n gpu_unlock)
 [[ $mod == */updates/dkms/gpu_unlock.ko* ]] || { echo 'Unexpected installed module.' >&2; exit 1; }
 [[ $(modinfo -k "$k" -F vermagic gpu_unlock) == "$k "* ]] || exit 1
 modinfo -k "$k" -p gpu_unlock | grep -q '^ad107_result:' || exit 1
 WORK=$(mktemp -d /var/tmp/gpu-unlock-dkms.XXXXXX)
 mkdir "$WORK/conf" "$WORK/audit"
 case "$mod" in
 *.zst) zstd -qdc "$mod" > "$WORK/expected.ko";;
 *.xz) xz -dc "$mod" > "$WORK/expected.ko";;
 *.gz) gzip -dc "$mod" > "$WORK/expected.ko";;
 *.ko) cp "$mod" "$WORK/expected.ko";;
 *) exit 1;; esac
 stamp=$(date -u +%Y%m%dT%H%M%S)-$$
 final="/boot/gpu-unlock-4060/$k-$stamp"
 mkdir "$WORK/publish"
 cp --reflink=auto "$dir/vmlinuz" "$WORK/publish/vmlinuz"
 dracut --conf /dev/null --confdir "$WORK/conf" --compress zstd --nostrip \
  --no-hostonly-cmdline --no-uefi --add systemd --add-drivers gpu_unlock \
  --omit-drivers 'nvidia nvidia_drm nvidia_modeset nvidia_uvm nvidia_peermem nouveau vfio_pci vfio_pci_core pci_stub xen_pciback pciback uio_pci_generic' \
  --install "$(command -v modprobe) $(command -v mkdir) /bin/sh" \
  --include "$LIB/image-overlay" / "$WORK/publish/initramfs.img" "$k" > "$LOG/build-$k.log" 2>&1
 (cd "$WORK/audit"; lsinitrd --unpack "$WORK/publish/initramfs.img")
 python3 "$LIB/verify-installed-image.py" "$WORK/audit" --kernel "$k" --module "$WORK/expected.ko" \
  --assets /usr/lib/firmware/gpu-unlock/610.43.03 --overlay "$LIB/image-overlay" > "$LOG/audit-$k.json"
 # Original images never touched; publish a new directory only after validation.
 [[ ! -e $final && ! -L $final ]] || exit 1
 mkdir "$final"
 install -m600 "$WORK/publish/vmlinuz" "$final/vmlinuz"
 install -m600 "$WORK/publish/initramfs.img" "$final/initramfs.img"
 sha256sum "$final/vmlinuz" "$final/initramfs.img" > "$final/SHA256SUMS"
 cat >> "$MENU" <<EOF
search --no-floppy --fs-uuid --set=unlock_modules_root $ROOT_UUID
if [ -f (\$unlock_modules_root)/usr/lib/modules/$k/pkgbase ]; then
menuentry 'EndeavourOS RTX 4060 unlocked (DKMS $k)' --class endeavouros --class gnu-linux --class os --id 'gpu-unlock-dkms-$k' {
    load_video
    set gfxpayload=keep
    insmod gzio
    insmod part_gpt
    insmod ext2
    search --no-floppy --fs-uuid --set=root $ROOT_UUID
    linux $final/vmlinuz $LINUX_CMDLINE gpu_unlock.targets=$TARGET_BDF gpu_unlock.ad107_experimental=1
    initrd $final/initramfs.img
}
fi
EOF
 rm -rf -- "$WORK";WORK=''
 count=$((count+1))
done
((count>0)) || { echo 'No matching installed kernel; retaining prior menu.' >&2; exit 1; }
grub-script-check "$MENU"
if [[ -f /boot/grub/gpu-unlock-4060.cfg ]]; then cp -a /boot/grub/gpu-unlock-4060.cfg /boot/grub/gpu-unlock-4060.cfg.previous; fi
chmod 600 "$MENU"
mv -f -- "$MENU" /boot/grub/gpu-unlock-4060.cfg
printf 'Published %s DKMS unlock entry/entries. Default unchanged; no reboot.\n' "$count"
