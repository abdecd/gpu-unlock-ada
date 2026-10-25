#!/bin/bash
# Remove this local installation. Never unload modules, edit GRUB or reboot.
set -euo pipefail
usage() {
 cat <<'EOF'
Usage: sudo bash local/cachyos/uninstall-host.sh [options]
  --dry-run        Show actions without changing the system
  --purge-images   Also delete audited *-nvidia-40-unlock.img files
  --purge-logs     Also delete /var/log/gpu-unlock-4060
  --help           Show usage
Default: remove hook, DKMS, source, tools and verified pinned firmware.
Keep boot images, logs, backups and user GRUB configuration.
EOF
}
dry=0;images=0;logs=0
for arg in "$@"; do
 case "$arg" in
 --dry-run) dry=1;; --purge-images) images=1;; --purge-logs) logs=1;;
 --help|-h) usage;exit 0;; *) usage >&2;exit 2;; esac
done
[[ $EUID == 0 ]] || { echo 'Run as root.' >&2;exit 1; }
exec 9>/run/lock/gpu-unlock-4060-update.lock
flock -n 9 || { echo 'Image updater is running; retry later.' >&2;exit 1; }
LIB=/usr/local/lib/gpu-unlock-4060
SRC=/usr/src/gpu-unlock-4060-local-1.1.1.ad107.1
FW=/usr/lib/firmware/gpu-unlock/610.43.03
LOG=/var/log/gpu-unlock-4060
HOOK=/etc/pacman.d/hooks/99-gpu-unlock-4060.hook
CONF=/etc/dracut.conf.d/zz-gpu-unlock-local-stock-omit.conf
# Refuse redirected cleanup paths.
for p in "$LIB" "$SRC" "$FW" "$LOG" "$HOOK" "$CONF" /etc/gpu-unlock-4060.conf; do
 [[ ! -L $p ]] || { echo "Refuse symlink: $p" >&2;exit 1; }
done
run() { printf '  ';printf '%q ' "$@";printf '\n';if ((!dry));then "$@";fi; }
# Inventory verified firmware before removing the installed manifest/source.
manifest="$LIB/artifacts-610.43.03.json"
[[ -f $manifest ]] || manifest="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)/firmware/artifacts-610.43.03.json"
fwlist=$(mktemp);imglist=$(mktemp)
trap 'rm -f -- "$fwlist" "$imglist"' EXIT
python3 - "$manifest" "$FW" > "$fwlist" <<'PY'
import hashlib,json,sys
from pathlib import Path
m=Path(sys.argv[1]);root=Path(sys.argv[2])
if not root.exists():raise SystemExit(0)
if not m.is_file():raise SystemExit('Firmware manifest missing; refusing removal')
d=json.loads(m.read_text());pins=dict(d['derived_assets'])
pins['gsp_ga10x.bin']=d['source_artifacts'][2]['firmware'][0]['sha256']
for k in ('generated_payload','generated_ad102_payload'):
 e=d[k];pins[e['filename']]=e['sha256']
notice=d['source_artifacts'][2].get('notice',{})
if 'sha256' in notice:pins['NVIDIA-LICENSE']=notice['sha256']
for name,h in pins.items():
 p=root/name
 if not p.exists() and not p.is_symlink():continue
 if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=h:
  raise SystemExit('Firmware changed; refusing removal: '+str(p))
 print(p)
unknown=[p.name for p in root.iterdir() if p.name not in pins]
if unknown:print('Keeping unowned firmware files: '+', '.join(unknown),file=sys.stderr)
PY
if ((images));then
 python3 - "$LOG" > "$imglist" <<'PY'
import hashlib,re,sys
from pathlib import Path
root=Path(sys.argv[1])
for record in sorted(root.glob('linux*-nvidia-40-unlock.sha256')):
 if record.is_symlink():raise SystemExit('Refuse symlink record')
 lines=record.read_text().splitlines()
 if len(lines)!=1:raise SystemExit('Invalid image checksum record')
 h,sep,path=lines[0].partition('  ')
 p=Path(path)
 if not sep or not re.fullmatch(r'/boot/initramfs-linux[A-Za-z0-9._+-]*-nvidia-40-unlock\.img',path):
  raise SystemExit('Unsafe image path: '+path)
 if not p.exists() and not p.is_symlink():continue
 if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=h:
  raise SystemExit('Image changed; refusing removal: '+path)
 print(path)
PY
fi
echo 'Remove automatic update hook:'
run rm -f -- "$HOOK"
state=$(dkms status -m gpu-unlock-4060-local -v 1.1.1.ad107.1 2>/dev/null || true)
if [[ -n $state || -d /var/lib/dkms/gpu-unlock-4060-local/1.1.1.ad107.1 ]];then
 echo 'Remove DKMS registration and installed modules:'
 run dkms remove -m gpu-unlock-4060-local -v 1.1.1.ad107.1 --all
fi
run rm -rf -- "$SRC"
run rm -f -- "$CONF" /etc/gpu-unlock-4060.conf
while IFS= read -r p;do [[ -z $p ]] || run rm -f -- "$p";done < "$fwlist"
if [[ -d $FW ]];then
 if ((dry));then echo "  Remove $FW if empty";else rmdir -- "$FW" 2>/dev/null || true;fi
fi
run rm -rf -- "$LIB"
while IFS= read -r p;do [[ -z $p ]] || run rm -f -- "$p";done < "$imglist"
if ((logs));then run rm -rf -- "$LOG";fi
echo 'GRUB, ordinary/fallback images, old TEST artifacts and workspace are unchanged.'
if ((!images));then echo 'Unlock images retained; remove unused GRUB entries yourself.';fi
if [[ -d /sys/module/gpu_unlock ]];then echo 'Loaded module/state remains until shutdown; do not rmmod. Next boot use an ordinary entry.';fi
((!dry)) || echo 'Dry run: nothing removed.'
