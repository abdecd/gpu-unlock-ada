"""Shared, hardware-free validation of target identity and firmware pins."""
import hashlib
import json
import re
from pathlib import Path

BINDER = re.compile(r'^(?:nvidia(?:[-_].*)?|nouveau|vfio[-_]pci(?:[-_]core)?|pci[-_]stub|(?:xen[-_])?pciback|uio[-_]pci[-_]generic)\.ko(?:\..*)?$')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pins(manifest):
    m = json.loads(Path(manifest).read_text())
    result = dict(m['derived_assets'])
    result['gsp_ga10x.bin'] = m['source_artifacts'][2]['firmware'][0]['sha256']
    for key in ('generated_payload', 'generated_ad102_payload'):
        item = m[key]
        result[item['filename']] = item['sha256']
    if len(result) != 9 or any(Path(n).name != n for n in result):
        raise ValueError('expected nine fixed firmware assets')
    return result


def verify_assets(directory, manifest):
    for name, sha in pins(manifest).items():
        p = Path(directory) / name
        if p.is_symlink() or not p.is_file() or digest(p) != sha:
            raise ValueError('invalid pinned firmware: ' + name)
