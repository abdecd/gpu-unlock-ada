import subprocess,unittest
from pathlib import Path
SCRIPT=Path(__file__).resolve().parents[1]/'uninstall-host.sh'
class UninstallTests(unittest.TestCase):
 def test_syntax(self):
  self.assertEqual(subprocess.run(['bash','-n',str(SCRIPT)],capture_output=True).returncode,0)
 def test_help_without_root(self):
  r=subprocess.run(['bash',str(SCRIPT),'--help'],capture_output=True,text=True)
  self.assertEqual(r.returncode,0)
  self.assertIn('--dry-run',r.stdout);self.assertIn('--purge-images',r.stdout)
 def test_unknown_argument(self):
  self.assertEqual(subprocess.run(['bash',str(SCRIPT),'--unknown'],capture_output=True).returncode,2)
 def test_hook_removed_before_dkms(self):
  s=SCRIPT.read_text();self.assertLess(s.index('run rm -f -- "$HOOK"'),s.index('run dkms remove'))
  self.assertIn('hashlib.sha256',s);self.assertIn('flock -n',s)
  self.assertNotIn('run rmmod',s);self.assertNotIn('run reboot',s)
if __name__=='__main__':unittest.main()
