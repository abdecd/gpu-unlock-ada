"""Run only a sandbox copy: all host paths and module loading are replaced."""
from pathlib import Path
import subprocess
import tempfile
import unittest

GATE = Path(__file__).resolve().parents[1] / 'image-overlay/usr/libexec/ad107-unlock-gate'
LOADER = 'modprobe -C /dev/null --ignore-install gpu_unlock targets=0000:01:00.0 ad107_experimental=1'


class GateIdentityTests(unittest.TestCase):
    def run_gate(self, vendor=None, device='0x28a0', bound=False, binder=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pci = root / 'sys/bus/pci/devices/0000:01:00.0'
            (root / 'proc').mkdir()
            (root / 'proc/cmdline').write_text(
                'gpu_unlock.targets=0000:01:00.0 gpu_unlock.ad107_experimental=1\n')
            if vendor is not None:
                pci.mkdir(parents=True)
                (pci / 'vendor').write_text(vendor + '\n')
                (pci / 'device').write_text(device + '\n')
                (pci / 'driver_override').write_text('(null)\n')
                if bound:
                    (pci / 'driver').mkdir()
            if binder:
                (root / 'sys/module/nvidia').mkdir(parents=True)
            text = GATE.read_text()
            self.assertEqual(text.count(LOADER), 1)
            text = text.replace(LOADER, 'printf attempted > "' + tmp + '/loaded"; false')
            for prefix in ('/run/', '/sys/', '/proc/'):
                text = text.replace(prefix, tmp + prefix)
            script = root / 'gate'
            script.write_text(text)
            result = subprocess.run(['sh', str(script)], capture_output=True, text=True)
            record = (root / 'run/ad107-experiment/result').read_text()
            return result.returncode, record, (root / 'loaded').exists()

    def test_absent(self):
        rc, record, loaded = self.run_gate()
        self.assertEqual(rc, 0)
        self.assertIn('SKIPPED:', record)
        self.assertFalse(loaded)

    def test_other_vendor_even_if_bound_and_binder_loaded(self):
        rc, record, loaded = self.run_gate('0x8086', bound=True, binder=True)
        self.assertEqual(rc, 0)
        self.assertIn('SKIPPED:', record)
        self.assertFalse(loaded)

    def test_other_nvidia_device(self):
        rc, record, loaded = self.run_gate('0x10de', '0x2d04')
        self.assertEqual(rc, 0)
        self.assertIn('SKIPPED:', record)
        self.assertFalse(loaded)

    def test_target_attempts_and_preserves_loader_failure(self):
        rc, record, loaded = self.run_gate('0x10de')
        self.assertNotEqual(rc, 0)
        self.assertIn('FAILED: modprobe returned', record)
        self.assertTrue(loaded)

    def test_target_bound_still_fails(self):
        rc, record, loaded = self.run_gate('0x10de', bound=True)
        self.assertNotEqual(rc, 0)
        self.assertIn('already bound', record)
        self.assertFalse(loaded)

    def test_target_binder_still_fails(self):
        rc, record, loaded = self.run_gate('0x10de', binder=True)
        self.assertNotEqual(rc, 0)
        self.assertIn('binder already loaded', record)
        self.assertFalse(loaded)
