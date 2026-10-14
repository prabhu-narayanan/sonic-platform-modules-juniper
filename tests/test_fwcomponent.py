"""Unit tests for sonic_platform/fwcomponent.py"""

import unittest
from unittest import mock

from tests.conftest import stub_sonic_platform_base, stub_sonic_platform_pddf_base, SONIC_PLATFORM_DIR, load_module

stub_sonic_platform_pddf_base()
mod = load_module("sp_fwcomponent", SONIC_PLATFORM_DIR / "fwcomponent.py")
impl_mod = load_module("sp_fwcomponent_impl", SONIC_PLATFORM_DIR / "impl_base" / "fwcomponent.py")


class TestFwComponent(unittest.TestCase):

    def _make(self, index=0, version="1.0.0"):
        fw_obj = mock.MagicMock()
        fw_obj.index = index
        fw_obj.get_name.return_value = "BIOS"
        fw_obj.get_description.return_value = "System BIOS"
        fw_obj.get_version.return_value = version
        fw_obj.install_firmware.return_value = True
        c = mod.FwComponent.__new__(mod.FwComponent)
        c._fw = fw_obj
        c._impl = impl_mod.FwComponentImplBase(c)
        return c

    def test_get_name(self):
        c = self._make()
        self.assertEqual(c.get_name(), "BIOS")

    def test_get_description(self):
        c = self._make()
        self.assertEqual(c.get_description(), "System BIOS")

    def test_get_firmware_version(self):
        c = self._make(version="2.1.3")
        self.assertEqual(c.get_firmware_version(), "2.1.3")

    def test_install_firmware(self):
        c = self._make()
        self.assertTrue(c.install_firmware("/path/to/image"))

    def test_update_firmware_delegates_to_install(self):
        c = self._make()
        self.assertTrue(c.update_firmware("/path/to/image"))

    def test_get_available_firmware_version(self):
        c = self._make(version="3.0.0")
        self.assertEqual(c.get_available_firmware_version("/img"), "3.0.0")

    def test_get_presence_index_0(self):
        c = self._make(index=0)
        self.assertTrue(c.get_presence())

    def test_get_presence_index_5(self):
        c = self._make(index=5)
        self.assertTrue(c.get_presence())

    def test_get_presence_other_index(self):
        c = self._make(index=2, version="1.0")
        self.assertTrue(c.get_presence())

    def test_get_status(self):
        c = self._make()
        self.assertTrue(c.get_status())

    def test_auto_update_returns_1(self):
        c = self._make()
        self.assertEqual(c.auto_update_firmware("/img", "cold"), 1)

    def test_get_model(self):
        c = self._make()
        self.assertEqual(c.get_model(), "NA")

    def test_get_serial(self):
        c = self._make()
        self.assertEqual(c.get_serial(), "NA")

    def test_get_revision(self):
        c = self._make()
        self.assertEqual(c.get_revision(), str(0))

    def test_get_position_in_parent(self):
        c = self._make(index=3)
        self.assertEqual(c.get_position_in_parent(), 3)

    def test_is_replaceable(self):
        c = self._make()
        self.assertFalse(c.is_replaceable())


if __name__ == "__main__":
    unittest.main()
