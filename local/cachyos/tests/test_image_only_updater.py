import subprocess,unittest
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
class ImageOnlyUpdater(unittest.TestCase):
 def test_shell_syntax(self):
  for name in ('update-images.sh','install-auto-update.sh'):
   self.assertEqual(subprocess.run(['bash','-n',str(BASE/name)],capture_output=True).returncode,0)
 def test_no_menu_or_stock_writes(self):
  s=(BASE/'update-images.sh').read_text()
  self.assertIn('out="/boot/initramfs-$pkg-nvidia-40-unlock.img"',s)
  self.assertNotIn('menuentry',s)
  self.assertNotIn('grub-script-check',s)
  self.assertNotIn('KERNEL_PKGBASE',s)
  self.assertIn('verify-installed-image.py',s)
  self.assertLess(s.index('verify-installed-image.py'),s.index('mv -f -- "$STAGED" "$out"'))
 def test_installer_no_grub(self):
  s=(BASE/'install-auto-update.sh').read_text()
  self.assertNotIn('/boot/grub',s)
  self.assertNotIn('grub-mkconfig',s)
if __name__=='__main__':unittest.main()
