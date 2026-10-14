"""Unit tests for sonic_platform/ssd.py"""

import unittest
from unittest import mock

from tests.conftest import SONIC_PLATFORM_DIR, load_module

mod = load_module("sp_ssd", SONIC_PLATFORM_DIR / "ssd.py")


class TestSsd(unittest.TestCase):

    def test_init(self):
        s = mod.Ssd(0)
        self.assertEqual(s.disk, 0)
        self.assertEqual(s.device, "/dev/nvme0")

    @mock.patch("subprocess.check_output",
                return_value="Device Model: test\nModel Number: PASCARI-NVMe-2TB something\nSerial: XYZ\n")
    def test_get_model_extracts_vendor(self, _):
        s = mod.Ssd(0)
        self.assertEqual(s.get_model(), "PASCARI")

    @mock.patch("subprocess.check_output", side_effect=Exception("fail"))
    def test_get_model_error(self, _):
        s = mod.Ssd(0)
        self.assertEqual(s.get_model(), "Not Available")

    @mock.patch("subprocess.check_output", return_value="no model line here\n")
    def test_get_model_no_match(self, _):
        s = mod.Ssd(0)
        self.assertEqual(s.get_model(), "Not Available")


if __name__ == "__main__":
    unittest.main()
