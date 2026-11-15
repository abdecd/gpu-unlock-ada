"""Execute only a rewritten sandbox copy; never source the real initramfs gate."""
from pathlib import Path
import subprocess
import tempfile
import unittest

GATE = Path(__file__).resolve().parents[1] / 'gate'
LOADER = 'modprobe -C /dev/null --ignore-install gpu_unlock "targets=$target"'


class GateSkipTests(unittest.TestCase):
    def run_gate(self, cmdline, binder=False, loaded=False, attempted=False, rc=0):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'proc').mkdir()
            (root / 'proc/cmdline').write_text(cmdline + '\n')
            (root / 'run/server3090').mkdir(parents=True)
            if attempted:
                (root / 'run/server3090/attempted').mkdir()
            if binder:
                (root / 'sys/module/nvidia').mkdir(parents=True)
            if loaded:
                (root / 'sys/module/gpu_unlock').mkdir(parents=True)
            text = GATE.read_text()
            self.assertEqual(text.count(LOADER), 1)
            text = text.replace('. /scripts/functions', 'panic() { echo "PANIC: $*"; }')
            text = text.replace('> /dev/kmsg', '')
            text = text.replace('command -v modprobe', 'command -v sh')
            text = text.replace(LOADER, 'mock_loader "$target"')
            text = text.replace('# Use the upstream', 'mock_loader() { echo "MOCK_LOAD: $1"; return ' + str(rc) + '; }\n# Use the upstream')
            for prefix in ('/proc/', '/run/', '/sys/'):
                text = text.replace(prefix, tmp + prefix)
            script = root / 'gate'
            script.write_text(text)
            result = subprocess.run(['sh', str(script)], capture_output=True, text=True)
            return result.returncode, result.stdout + result.stderr

    def test_safe_skips(self):
        cases = [('', {}), ('gpu_unlock.targets=', {}),
                 ('gpu_unlock.targets=bad', {}),
                 ('gpu_unlock.targets=all gpu_unlock.targets=all', {}),
                 ('gpu_unlock.targets=all', {'binder': True}),
                 ('gpu_unlock.targets=all', {'loaded': True}),
                 ('gpu_unlock.targets=all', {'attempted': True})]
        for cmd, options in cases:
            with self.subTest(cmd=cmd, options=options):
                rc, text = self.run_gate(cmd, **options)
                self.assertEqual(rc, 0, text)
                self.assertIn('SKIPPED:', text)
                self.assertNotIn('MOCK_LOAD:', text)
                self.assertNotIn('PANIC:', text)

    def test_single_multi_all_passed_unchanged(self):
        for target in ('0000:01:00.0', '0000:01:00.0,0000:02:00.0', 'all'):
            rc, text = self.run_gate('gpu_unlock.targets=' + target)
            self.assertEqual(rc, 0, text)
            self.assertIn('MOCK_LOAD: ' + target, text)
            self.assertIn('MODULE_RETURNED:', text)

    def test_loader_failure_not_treated_as_safe_skip(self):
        rc, text = self.run_gate('gpu_unlock.targets=all', rc=1)
        self.assertNotEqual(rc, 0)
        self.assertIn('FAILED_AFTER_LOAD:', text)
        self.assertIn('PANIC:', text)
        self.assertNotIn('SKIPPED:', text)
