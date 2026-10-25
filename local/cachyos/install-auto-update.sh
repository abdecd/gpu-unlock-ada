#!/bin/bash
# Install image-only automation; no GRUB menu/config generation.
set -euo pipefail
BASE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
[[ $EUID == 0 ]] || exit 1
DEST=/usr/local/lib/gpu-unlock-4060
[[ ! -L $DEST ]] || exit 1
install -d -m755 "$DEST" /etc/pacman.d/hooks
install -m755 "$BASE/update-images.sh" "$BASE/verify-installed-image.py" "$DEST/"
install -m644 "$BASE/../../firmware/artifacts-610.43.03.json" "$DEST/"
# Replace only the owned overlay tree, not arbitrary user configuration.
[[ ! -L $DEST/image-overlay ]] || exit 1
rm -rf -- "$DEST/image-overlay"
cp -a "$BASE/image-overlay" "$DEST/"
chown -R root:root "$DEST"
find "$DEST" -type d -exec chmod 755 {} +
install -m644 "$BASE/99-gpu-unlock-4060.hook" /etc/pacman.d/hooks/99-gpu-unlock-4060.hook
"$DEST/update-images.sh"
echo 'Image-only automation installed. Configure GRUB yourself; no menu written.'
