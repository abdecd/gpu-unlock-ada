#!/bin/bash
# Install root-owned automation, preserving original/default and TEST entries.
set -euo pipefail
BASE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
[[ $EUID == 0 ]] || exit 1
DEST=/usr/local/lib/gpu-unlock-4060
CONF=/etc/gpu-unlock-4060.conf
HOOK=/etc/pacman.d/hooks/99-gpu-unlock-4060.hook
for f in "$DEST" "$CONF" "$HOOK"; do [[ ! -e $f && ! -L $f ]] || { echo "Refuse existing $f" >&2; exit 1; }; done
# Current host has /boot on ext4 root; do not generalize path assumptions.
[[ $(findmnt -n -o TARGET -T /boot) == / && $(findmnt -n -o FSTYPE -T /boot) == ext4 ]] || { echo 'Separate /boot needs adapted GRUB path.' >&2; exit 1; }
grep -q 'source .*custom.cfg' /boot/grub/grub.cfg
python3 - "$CONF" <<'PY'
import pathlib,shlex,sys,re
s=pathlib.Path('/boot/grub/custom.cfg').read_text()
# Reuse the already tested root and arguments, not the running /proc command
# line, which may contain transient boot flags.
lines=[l.strip() for l in s.splitlines() if l.strip().startswith('linux\t') or l.strip().startswith('linux ')]
lines=[l for l in lines if 'vmlinuz-linux-cachyos-ad107-7.3.0-4' in l]
if len(lines)!=1:raise SystemExit('Cannot identify verified TEST baseline')
a=lines[0].split();args=[x for x in a[2:] if not x.startswith('gpu_unlock.')]
roots=[x.split('=',2)[2] for x in args if x.startswith('root=UUID=')]
if len(roots)!=1 or not re.fullmatch('[a-fA-F0-9-]+',roots[0]):raise SystemExit('Invalid root UUID')
out='KERNEL_PKGBASE=linux-cachyos\nTARGET_BDF=0000:01:00.0\nROOT_UUID='+shlex.quote(roots[0])+'\nLINUX_CMDLINE='+shlex.quote(' '.join(args))+'\n'
p=pathlib.Path(sys.argv[1]);p.write_text(out);p.chmod(0o600)
PY
install -d -m755 "$DEST" /etc/pacman.d/hooks
install -m755 "$BASE/update-images.sh" "$BASE/verify-installed-image.py" "$DEST/"
install -m644 "$BASE/../../firmware/artifacts-610.43.03.json" "$DEST/"
cp -a "$BASE/image-overlay" "$DEST/"
chown -R root:root "$DEST"
find "$DEST" -type d -exec chmod 755 {} +
# Build first. Hook and GRUB include are published only after initial build pass.
"$DEST/update-images.sh"
cp -a /boot/grub/custom.cfg /boot/grub/custom.cfg.before-dkms-unlock
python3 - <<'PY'
from pathlib import Path
p=Path('/boot/grub/custom.cfg');s=p.read_text();tag='# BEGIN GPU-UNLOCK-4060 DKMS MANAGED INCLUDE'
if tag in s:raise SystemExit('Include already exists')
s+='\n'+tag+'\nif [ -f $prefix/gpu-unlock-4060.cfg ]; then\n    source $prefix/gpu-unlock-4060.cfg\nfi\n# END GPU-UNLOCK-4060 DKMS MANAGED INCLUDE\n'
q=Path('/boot/grub/.custom.cfg.dkms-new');q.write_text(s);q.chmod(0o600)
PY
grub-script-check /boot/grub/.custom.cfg.dkms-new
mv /boot/grub/.custom.cfg.dkms-new /boot/grub/custom.cfg
install -m644 "$BASE/99-gpu-unlock-4060.hook" "$HOOK"
echo 'DKMS image automation installed. Existing TEST retained; no default or reboot change.'
