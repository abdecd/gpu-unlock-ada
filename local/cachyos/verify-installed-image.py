#!/usr/bin/env python3
"""Fail-closed static audit of an extracted initramfs; never loads a module."""
import argparse
import hashlib
import gzip
import lzma
import json
import os
import re
import stat
import subprocess
from pathlib import Path

GATE = 'gpu-unlock-ad107.service'
BINDER = re.compile(r'^(?:nvidia(?:[-_].*)?|nouveau|vfio[-_]pci(?:[-_]core)?|pci[-_]stub|(?:xen[-_])?pciback|uio[-_]pci[-_]generic)\.ko(?:\..*)?$')

def require(ok, message):
    if not ok:
        raise RuntimeError(message)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def image_path(root, rel):
    """Resolve links as the image kernel would, never against the host root."""
    todo = str(rel).split('/')
    parts = []
    links = 0
    while todo:
        part = todo.pop(0)
        if part in ('', '.'):
            continue
        if part == '..':
            require(bool(parts), 'Image path escapes root: ' + str(rel))
            parts.pop()
            continue
        q = root.joinpath(*parts, part)
        if q.is_symlink():
            links += 1
            require(links <= 40, 'Symlink loop: ' + str(rel))
            target = os.readlink(q)
            if target.startswith('/'):
                parts = []
            todo = target.split('/') + todo
        else:
            parts.append(part)
    return root.joinpath(*parts)

def unit_settings(path):
    result = {}
    section = ''
    pending = ''
    for raw in path.read_text().splitlines():
        line = pending + raw.strip()
        if line.endswith('\\'):
            pending = line[:-1] + ' '
            continue
        pending = ''
        if not line or line.startswith(('#', ';')):
            continue
        if line.startswith('[') and line.endswith(']'):
            section = line[1:-1]
        elif '=' in line:
            key, value = line.split('=', 1)
            key = (section, key.strip())
            if not value.strip():
                result[key] = []
            else:
                result.setdefault(key, []).append(value.strip())
    require(not pending, 'Incomplete unit continuation: ' + str(path))
    return result

def normalized_module_bytes(path):
    """Remove transport compression only; preserve ELF and appended signatures."""
    path = Path(path)
    if path.suffix == '.gz':
        return gzip.decompress(path.read_bytes())
    if path.suffix == '.xz':
        return lzma.decompress(path.read_bytes())
    if path.suffix == '.zst':
        return subprocess.run(['zstd', '-dc', '--', str(path)], check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
    require(path.suffix == '.ko', 'Unsupported module format: ' + str(path))
    return path.read_bytes()


def normalized_module_sha(path):
    return hashlib.sha256(normalized_module_bytes(path)).hexdigest()


def asset_pins():
    manifest = Path(__file__).resolve().parent/'artifacts-610.43.03.json'
    if not manifest.is_file():
        manifest = Path(__file__).resolve().parents[2]/'firmware/artifacts-610.43.03.json'
    data = json.loads(manifest.read_text())
    pins = dict(data['derived_assets'])
    pins['gsp_ga10x.bin'] = data['source_artifacts'][2]['firmware'][0]['sha256']
    for key in ('generated_payload', 'generated_ad102_payload'):
        entry = data[key]
        pins[entry['filename']] = entry['sha256']
    require(len(pins) == 9, 'Expected exactly nine pinned firmware inputs')
    return pins


def effective_unit(root, name):
    paths = [image_path(root, prefix + '/systemd/system')/name
             for prefix in ('etc', 'run', 'usr/lib')]
    selected = next((p for p in paths if p.exists() or p.is_symlink()), None)
    require(selected is not None, 'Missing unit: ' + name)
    q = image_path(root, selected.relative_to(root))
    require(q.is_file(), 'Masked/missing unit: ' + name)
    settings = unit_settings(q)
    drops = []
    for prefix in ('usr/lib', 'run', 'etc'):
        d = image_path(root, prefix + '/systemd/system/' + name + '.d')
        drops += list(d.glob('*.conf')) if d.is_dir() else []
    # Duplicate basenames have precedence rules: disallow ambiguity.
    require(len({p.name for p in drops}) == len(drops), 'Ambiguous drop-ins: ' + name)
    for drop in sorted(drops, key=lambda p: p.name):
        q = image_path(root, drop.relative_to(root))
        require(q.is_file(), 'Masked/missing drop-in: ' + str(drop))
        for key, value in unit_settings(q).items():
            settings[key] = value if not value else settings.get(key, []) + value
    return settings

def audit(root, kernel, expected_module, assets, overlay):
    require(kernel not in ('', '.', '..') and '/' not in kernel,
            'Invalid kernel release')
    root = root.absolute()
    require(root.is_dir() and not root.is_symlink(), 'Invalid extraction root')
    def locate(rel):
        q = image_path(root, rel)
        require(q.is_file(), 'Missing image file: ' + rel)
        return q
    # Walk without following directory symlinks; never open host link targets.
    for path in root.rglob('*'):
        if BINDER.match(path.name):
            raise RuntimeError('Forbidden binder in image: ' + str(path))
    module_dir = f'usr/lib/modules/{kernel}/updates/dkms/'
    candidates = []
    for suffix in ('', '.zst', '.xz', '.gz'):
        q = image_path(root, module_dir + 'gpu_unlock.ko' + suffix)
        if q.exists() or q.is_symlink():
            require(q.is_file(), 'Invalid image module: ' + str(q))
            candidates.append(q)
    require(len(candidates) == 1, 'Missing/duplicate installed module')
    module = candidates[0]
    require(normalized_module_sha(module) == normalized_module_sha(expected_module),
            'Module mismatch (uncompressed bytes, including signature)')
    copies = [p for p in root.rglob('gpu_unlock.ko*') if not p.is_dir()]
    require(len(copies) == 1 and image_path(root, copies[0].relative_to(root)) == module,
            'Missing/duplicate installed module')
    for name, expected in sorted(asset_pins().items()):
        source = assets/name
        require(source.is_file() and not source.is_symlink() and sha(source) == expected,
                'Invalid pinned asset: ' + name)
        require(sha(locate('usr/lib/firmware/gpu-unlock/610.43.03/' + name)) == expected,
                'Firmware mismatch: ' + name)
    ov = overlay
    require(ov.is_dir(), 'Mandatory overlay missing')
    for f in ov.rglob('*'):
        rel = f.relative_to(ov)
        # Compare links as links, including broken/masked links; do not hash host targets.
        if f.is_symlink():
            q = image_path(root, rel.parent)/rel.name
            require(q.is_symlink() and os.readlink(q) == os.readlink(f), 'Overlay symlink mismatch: ' + str(rel))
        elif f.is_file():
            q = locate(str(rel))
            require(sha(q) == sha(f), 'Overlay mismatch: ' + str(rel))
            require(stat.S_IMODE(q.stat().st_mode) == stat.S_IMODE(f.stat().st_mode), 'Overlay permissions mismatch: ' + str(rel))
    locate('etc/initrd-release')
    locate('usr/lib/systemd/system/initrd-switch-root.service')
    helper = locate('usr/libexec/ad107-unlock-gate')
    require(helper.stat().st_mode & 0o111, 'Gate helper not executable')
    # Pin literal opt-ins and explicit non-skipping validation, in addition to the seal.
    text = helper.read_text()
    for token in ('/proc/cmdline', 'gpu_unlock.targets=0000:01:00.0', 'gpu_unlock.ad107_experimental=1',
                  '"$target_count" -eq 1', '"$optin_count" -eq 1',
                  'targets=0000:01:00.0 ad107_experimental=1', '"$value" = 3', 'pci-stub.*|pci_stub.*)', 'read_single "$pci/driver_override"'):
        require(token in text, 'Missing mandatory gate flag/outcome check: ' + token)
    # systemd searches /etc first. Reject extra gate drop-ins rather than trying
    # to approximate arbitrary systemd merging/specifier semantics.
    service = effective_unit(root, GATE)
    for key, value in ((('Unit','DefaultDependencies'),'no'), (('Service','Type'),'oneshot'),
                       (('Service','RemainAfterExit'),'yes'), (('Service','Restart'),'no')):
        require(service.get(key) == [value], 'Unsafe gate unit setting: ' + str(key))
    require(service.get(('Service','ExecStart')) == ['/usr/libexec/ad107-unlock-gate'], 'Unsafe gate ExecStart')
    for section, key in service:
        require(not key.startswith(('Condition','Assert')) and key not in ('ExecCondition','SuccessExitStatus','ExecStartPre','ExecStartPost'), 'Gate can skip/override verification: ' + key)
    for name in ('dracut-pre-udev.service', 'initrd-switch-root.service', 'initrd-switch-root.target'):
        settings = effective_unit(root, name)
        for key in ('Requires','After'):
            require(GATE in ' '.join(settings.get(('Unit',key), [])).split(), name + ' lacks mandatory ' + key + ' gate')
    # The target kernel's actual host metadata is authoritative for builtins;
    # image copies may be pruned. Never silently skip a missing inventory.
    built = Path('/usr/lib/modules')/kernel/'modules.builtin'
    require(built.is_file(), 'Missing target-kernel modules.builtin')
    exceptions = []
    for line in built.read_text().splitlines():
        # Reviewed exception: pci-stub has an empty default ID table; the
        # pinned gate rejects every pci-stub/pci_stub cmdline option and
        # refuses any bound/driver_override target. Other binders fail closed.
        if Path(line).name == 'pci-stub.ko':
            exceptions.append(line)
            continue
        require(not BINDER.match(Path(line).name), 'Built-in binder: ' + line)
    print(json.dumps({'image_audit_passed': True, 'firmware_files': 9, 'kernel': kernel,
                      'reviewed_inert_builtin_exceptions': exceptions,
                      'note': 'Static contents only; not proof of boot or AD107 compatibility'}, indent=2))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    parser.add_argument('--kernel', required=True)
    parser.add_argument('--module', type=Path, required=True, help='Expected normalized installed .ko (including signature)')
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--overlay', type=Path, required=True)
    args = parser.parse_args()
    try:
        audit(args.root, args.kernel, args.module, args.assets, args.overlay)
    except (RuntimeError, OSError, ValueError, lzma.LZMAError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"Image audit failed: {exc}\n")
