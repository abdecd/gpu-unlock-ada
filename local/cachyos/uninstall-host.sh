#!/bin/bash
# No unload/reload and no boot image deletion; preserves known-good TEST entry.
set -euo pipefail
[[ $EUID == 0 ]] || exit 1
dkms remove -m gpu-unlock-4060-local -v 1.1.1.ad107.1 --all
rm -rf -- /usr/src/gpu-unlock-4060-local-1.1.1.ad107.1
rm -f -- /etc/dracut.conf.d/zz-gpu-unlock-local-stock-omit.conf
# Fixed firmware may also be used by separately-built images; leave in place.
echo 'DKMS registration/source removed. Pinned firmware and existing TEST image retained.'
echo 'A module already loaded remains loaded until reboot; do not rmmod a live GPU experiment.'
