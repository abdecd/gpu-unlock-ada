# SPDX-License-Identifier: GPL-2.0-only
"""The read-only helper never suggests AD107M without explicit inclusion."""
import importlib.util
from pathlib import Path
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location(
    "boot_option", Path(__file__).resolve().parents[1] / "tools/print_boot_option.py")
boot_option = importlib.util.module_from_spec(spec)
spec.loader.exec_module(boot_option)

PCI = """0000:0A:00.0 VGA compatible controller: NVIDIA [10de:28a0]
0000:0b:00.0 VGA compatible controller: NVIDIA [10de:28a1]
0000:02:00.0 VGA compatible controller: NVIDIA [10de:2684]
"""


class BootOptionTests(unittest.TestCase):
    def test_exact28a0_is_optional_and_not_a_family_match(self):
        self.assertEqual(boot_option.candidates(PCI), [("0000:02:00.0", "2684")])
        self.assertEqual(boot_option.candidates(PCI, True),
                         [("0000:0a:00.0", "28a0"), ("0000:02:00.0", "2684")])

    def test_exact28a0_prints_separate_guarded_option(self):
        with mock.patch("sys.argv", ["print_boot_option.py", "--exact28a0"]), \
                mock.patch.object(boot_option.subprocess, "run") as run, \
                mock.patch("builtins.print") as output:
            run.return_value.stdout = PCI
            self.assertEqual(boot_option.main(), 0)
            run.assert_called_once_with(["lspci", "-Dnn"], check=True,
                                        capture_output=True, text=True, timeout=10)
            output.assert_any_call("gpu_unlock.targets=0000:0a:00.0 "
                                   "gpu_unlock.ad107_experimental=1")
