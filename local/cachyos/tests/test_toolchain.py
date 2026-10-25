import os,subprocess,tempfile,unittest
from pathlib import Path
HELPER=Path(__file__).resolve().parents[1]/'dkms-build.sh'
class ToolchainTests(unittest.TestCase):
 def check_mode(self,config,expected):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'kernel').mkdir();(p/'kernel/.config').write_text(config)
   (p/'make').write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n');(p/'make').chmod(0o755)
   env=dict(os.environ,PATH=d+':'+os.environ['PATH'])
   r=subprocess.run(['bash',str(HELPER),str(p/'kernel'),'LLVM=1'],env=env,capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr);self.assertIn(expected,r.stdout.splitlines())
 def test_clang(self):self.check_mode('CONFIG_CC_IS_CLANG=y\n','LLVM=1')
 def test_gcc(self):self.check_mode('CONFIG_CC_IS_GCC=y\n','LLVM=')
 def test_missing_config(self):
  with tempfile.TemporaryDirectory() as d:
   r=subprocess.run(['bash',str(HELPER),d],capture_output=True,text=True);self.assertNotEqual(r.returncode,0)
if __name__=='__main__':unittest.main()
