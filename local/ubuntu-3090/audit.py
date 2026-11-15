#!/usr/bin/env python3
"""Audit unpacked image without resolving absolute symlinks against the host."""
import argparse
import json
import re
from pathlib import Path
from common import BINDER, digest, pins


def audit(root, kernel, module, lib):
    root, lib = Path(root), Path(lib)
    # Inspect regular archive entries only; never follow an image symlink.
    def entries(directory):
        for p in directory.iterdir():
            if p.is_symlink():
                continue
            if p.is_dir():
                yield from entries(p)
            elif p.is_file():
                yield p
    files = list(entries(root))
    def suffix(s):
        found = [p for p in files if str(p.relative_to(root)).endswith(s)]
        if len(found) != 1:
            raise ValueError('missing/ambiguous image file: ' + s)
        return found[0]
    modules = [p for p in files if re.search(r'\.ko(?:\..*)?$', p.name)]
    for p in modules:
        if BINDER.fullmatch(p.name):
            raise ValueError('GPU binder present: ' + str(p))
    unlocks = [p for p in modules if p.name.startswith('gpu_unlock.ko')]
    expected = suffix(f'lib/modules/{kernel}/extra/server3090/gpu_unlock.ko')
    if unlocks != [expected] or digest(expected) != digest(module):
        raise ValueError('unexpected unlock module content/count')
    if digest(suffix('scripts/init-top/00-server3090')) != digest(lib / 'gate'):
        raise ValueError('gate mismatch')
    order = suffix('scripts/init-top/ORDER').read_text()
    lines = [l for l in order.splitlines() if l and not l.startswith('#')]
    gate = next((i for i, l in enumerate(lines) if re.search(r'/00-server3090(?:\s|$)', l)), None)
    udev = next((i for i, l in enumerate(lines) if re.search(r'/udev(?:\s|$)', l)), None)
    if gate is None or udev is None or gate >= udev:
        raise ValueError('gate not ordered before udev: ' + repr(order))
    for name, sha in pins(lib / 'artifacts.json').items():
        if digest(suffix('lib/firmware/gpu-unlock/610.43.03/' + name)) != sha:
            raise ValueError('firmware mismatch: ' + name)
    # An upstream integration may insert another early loader; refuse it.
    for p in files:
        rel = str(p.relative_to(root))
        if (rel.endswith('/conf/modules') or rel == 'conf/modules' or '/scripts/' in '/' + rel) and p != suffix('scripts/init-top/00-server3090'):
            if b'gpu_unlock' in p.read_bytes():
                raise ValueError('other unlock loader/reference: ' + rel)
    return {'audit_passed': True, 'kernel': kernel,
            'note': 'static audit only; not boot or hardware validation'}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    for arg in ('root', 'kernel', 'module', 'lib'):
        p.add_argument('--' + arg, required=True)
    a = p.parse_args()
    print(json.dumps(audit(a.root, a.kernel, a.module, a.lib), indent=2))
