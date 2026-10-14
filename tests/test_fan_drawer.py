"""Unit tests for sonic_platform/fan_drawer.py"""

import unittest
from unittest import mock

from tests.conftest import stub_sonic_platform_base, stub_sonic_platform_pddf_base, stub_sonic_py_common, SONIC_PLATFORM_DIR, load_module

stub_sonic_platform_pddf_base()
stub_sonic_py_common()

# Stub the relative import of .fan inside fan_drawer
import sys, types
sp_pkg = types.ModuleType("sonic_platform")
sp_pkg.__path__ = [str(SONIC_PLATFORM_DIR)]
sys.modules.setdefault("sonic_platform", sp_pkg)
fan_stub = types.ModuleType("sonic_platform.fan")
fan_stub.Fan = mock.MagicMock()
sys.modules["sonic_platform.fan"] = fan_stub

mod = load_module("sonic_platform.fan_drawer", SONIC_PLATFORM_DIR / "fan_drawer.py",
                  package="sonic_platform")
impl_mod = load_module("fd_impl", SONIC_PLATFORM_DIR / "impl_base" / "fan_drawer.py")


class TestFanDrawer(unittest.TestCase):

    def _make(self, fan_list=None):
        fd = mod.FanDrawer.__new__(mod.FanDrawer)
        fd._fan_list = fan_list or []
        fd._impl = impl_mod.FanDrawerImplBase(fd)
        return fd

    def test_get_model_no_fans(self):
        fd = self._make()
        self.assertEqual(fd.get_model(), 'N/A')

    def test_get_serial_no_fans(self):
        fd = self._make()
        self.assertEqual(fd.get_serial(), 'N/A')

    def test_get_model_delegates_to_first_fan(self):
        fan = mock.MagicMock()
        fan.get_model.return_value = 'FAN-MODEL-X'
        fd = self._make(fan_list=[fan])
        self.assertEqual(fd.get_model(), 'FAN-MODEL-X')

    def test_get_serial_delegates_to_first_fan(self):
        fan = mock.MagicMock()
        fan.get_serial.return_value = 'SN-12345'
        fd = self._make(fan_list=[fan])
        self.assertEqual(fd.get_serial(), 'SN-12345')


if __name__ == "__main__":
    unittest.main()
