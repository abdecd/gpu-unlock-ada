import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from common import BINDER
from audit import audit
from unittest.mock import patch
import hashlib


class IsolationTests(unittest.TestCase):
    def test_shell_syntax(self):
        for name in ('gate', 'image-hook', 'build-image.sh'):
            subprocess.run(['bash' if name.endswith('.sh') else 'sh', '-n', str(BASE / name)], check=True)

    def test_no_host_activation(self):
        text = (BASE / 'build-image.sh').read_text()
        for forbidden in ('update-initramfs -u', 'grub-mkconfig', 'update-grub',
                          'dkms install', 'dkms add', 'modprobe gpu_unlock'):
            self.assertNotIn(forbidden, '\n'.join(l for l in text.splitlines() if not l.startswith('#')))
        self.assertIn('sha256sum -c "$WORK/stock.sha256"', text)
        self.assertIn('audit.py', text)
        self.assertLess(text.index('audit.py" --root'), text.index('mv -f --'))

    def test_binders(self):
        for name in ('nvidia.ko', 'nvidia_drm.ko.zst', 'nouveau.ko', 'vfio-pci.ko', 'vfio_pci_core.ko.xz', 'pci_stub.ko', 'xen-pciback.ko'):
            self.assertRegex(name, BINDER)
        self.assertNotRegex('i915.ko', BINDER)

    def test_gate_contract(self):
        text = (BASE / 'gate').read_text()
        self.assertIn('gpu_unlock.targets=*)', text)
        self.assertIn('all)', text)
        self.assertIn('SKIPPED: no targets', text)
        self.assertNotIn('server3090-target', text)
        self.assertNotIn('server3090.enable', text)
        self.assertEqual(text.count('modprobe -C /dev/null'), 1)
        self.assertNotIn('gpu_unlock.server3090=1)', text)
        self.assertIn('not proof of unlock', text)

    def test_build_does_not_access_gpu(self):
        text = (BASE / 'build-image.sh').read_text()
        self.assertNotIn('/sys/bus/pci', text)
        self.assertNotIn('nvidia-smi', text)

    def test_synthetic_image_audit_and_rejections(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root, lib = base / 'image', base / 'lib'
            lib.mkdir()
            (lib / 'gate').write_text('gate')
            module = base / 'module.ko'
            module.write_text('module')
            def put(rel, data):
                p = root / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(data)
                return p
            put('main/lib/modules/test/extra/server3090/gpu_unlock.ko', 'module')
            put('main/scripts/init-top/00-server3090', 'gate')
            order = put('main/scripts/init-top/ORDER', '/scripts/init-top/00-server3090\n/scripts/init-top/udev\n')
            put('main/lib/firmware/gpu-unlock/610.43.03/asset.bin', 'firmware')
            with patch('audit.pins', return_value={'asset.bin': hashlib.sha256(b'firmware').hexdigest()}):
                self.assertTrue(audit(root, 'test', module, lib)['audit_passed'])
                binder = put('main/lib/modules/test/nvidia.ko', 'bad')
                with self.assertRaisesRegex(ValueError, 'binder'):
                    audit(root, 'test', module, lib)
                binder.unlink()
                order.write_text('/scripts/init-top/udev\n/scripts/init-top/00-server3090\n')
                with self.assertRaisesRegex(ValueError, 'ordered'):
                    audit(root, 'test', module, lib)


if __name__ == '__main__':
    unittest.main()
