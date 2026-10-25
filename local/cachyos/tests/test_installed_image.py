"""Hardware-free installed-image checks; never execute the overlay or load a module."""
import gzip
import hashlib
import importlib.util
import lzma
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

VERIFIER = Path(__file__).resolve().parents[1]/'verify-installed-image.py'
spec = importlib.util.spec_from_file_location('installed_image', VERIFIER)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


class InstalledImageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def put(self, rel, data=b''):
        path = self.root/rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def link(self, rel, target):
        path = self.root/rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(target)
        return path

    def test_normalize_plain_gzip_xz_preserves_signature(self):
        payload = b'\x7fELF\x00module\x00signed bytes~Module signature appended~\n'
        digest = hashlib.sha256(payload).hexdigest()
        for suffix, encoded in (('', payload), ('.gz', gzip.compress(payload)),
                                ('.xz', lzma.compress(payload))):
            with self.subTest(suffix=suffix):
                path = self.put('gpu_unlock.ko' + suffix, encoded)
                self.assertEqual(verifier.normalized_module_bytes(path), payload)
                self.assertEqual(verifier.normalized_module_sha(path), digest)
        changed = self.put('other.ko', payload + b'changed signature')
        self.assertNotEqual(verifier.normalized_module_sha(changed), digest)

    @unittest.skipUnless(shutil.which('zstd'), 'zstd is not installed')
    def test_normalize_zstd(self):
        payload = b'\x7fELFsigned module\x00' * 20
        encoded = subprocess.run(['zstd', '-q', '-c'], input=payload,
                                 check=True, stdout=subprocess.PIPE).stdout
        self.assertEqual(verifier.normalized_module_bytes(
            self.put('gpu_unlock.ko.zst', encoded)), payload)

    def test_bad_compression_fails(self):
        for suffix in ('.gz', '.xz'):
            with self.subTest(suffix=suffix):
                with self.assertRaises((OSError, EOFError, lzma.LZMAError)):
                    verifier.normalized_module_bytes(self.put('gpu_unlock.ko' + suffix, b'bad'))

    def test_absolute_and_relative_symlinks_stay_inside_image(self):
        expected = self.put('usr/lib/item', b'image only')
        self.link('lib', '/usr/lib')
        self.link('usr/lib/alias', '../lib/item')
        self.assertEqual(verifier.image_path(self.root, '/lib/alias'), expected)
        self.assertEqual(verifier.image_path(self.root, 'lib/../lib/item'), expected)
        self.link('host-looking', '/etc/passwd')
        self.assertEqual(verifier.image_path(self.root, 'host-looking'), self.root/'etc/passwd')
        self.assertFalse(verifier.image_path(self.root, 'host-looking').exists())

    def test_symlink_escape_and_loop_rejected(self):
        self.link('escape', '../outside')
        self.link('loop', '/loop')
        for rel in ('escape', 'loop', '../outside'):
            with self.subTest(rel=rel), self.assertRaises(RuntimeError):
                verifier.image_path(self.root, rel)

    def test_effective_unit_and_dropin_resolve_image_links(self):
        self.put('usr/lib/systemd/system/demo.service', b'[Service]\nType=oneshot\n')
        self.put('etc/units/demo.service', b'[Service]\nType=simple\n')
        self.link('etc/systemd/system/demo.service', '/etc/units/demo.service')
        self.put('etc/units/override.conf', b'[Service]\nRestart=no\n')
        self.link('etc/systemd/system/demo.service.d/10-test.conf', '/etc/units/override.conf')
        settings = verifier.effective_unit(self.root, 'demo.service')
        self.assertEqual(settings[('Service', 'Type')], ['simple'])
        self.assertEqual(settings[('Service', 'Restart')], ['no'])
        (self.root/'etc/units/override.conf').unlink()
        with self.assertRaisesRegex(RuntimeError, 'Masked/missing drop-in'):
            verifier.effective_unit(self.root, 'demo.service')

    def test_effective_mask_and_ambiguous_dropins_rejected(self):
        self.put('usr/lib/systemd/system/demo.service', b'[Service]\nType=oneshot\n')
        mask = self.link('etc/systemd/system/demo.service', '/dev/null')
        with self.assertRaisesRegex(RuntimeError, 'Masked/missing unit'):
            verifier.effective_unit(self.root, 'demo.service')
        mask.unlink()
        for prefix in ('etc', 'usr/lib'):
            self.put(prefix + '/systemd/system/demo.service.d/10-test.conf', b'[Unit]\nAfter=a\n')
        with self.assertRaisesRegex(RuntimeError, 'Ambiguous drop-ins'):
            verifier.effective_unit(self.root, 'demo.service')

    def test_forbidden_binders_static_temp_image(self):
        names = ('nvidia.ko', 'nvidia_drm.ko.zst', 'nvidia-modeset.ko.gz',
                 'nouveau.ko.xz', 'vfio_pci.ko', 'vfio-pci-core.ko.zst',
                 'pci-stub.ko', 'pci_stub.ko.gz', 'xen-pciback.ko',
                 'pciback.ko.xz', 'uio_pci_generic.ko')
        for name in names:
            with self.subTest(name=name):
                path = self.put('usr/lib/modules/test/kernel/' + name)
                with self.assertRaisesRegex(RuntimeError, 'Forbidden binder in image'):
                    verifier.audit(self.root, 'test', self.root/'expected.ko',
                                   self.root/'assets', self.root/'overlay')
                path.unlink()
        # Even a dangling binder link must not evade the inventory.
        self.link('nouveau.ko.gz', '/missing')
        with self.assertRaisesRegex(RuntimeError, 'Forbidden binder in image'):
            verifier.audit(self.root, 'test', self.root/'expected.ko',
                           self.root/'assets', self.root/'overlay')

    def test_nine_fixed_asset_pins(self):
        pins = verifier.asset_pins()
        self.assertEqual(len(pins), 9)
        self.assertTrue(all(len(digest) == 64 for digest in pins.values()))
        self.assertIn('gsp_ga10x.bin', pins)


if __name__ == '__main__':
    unittest.main()
