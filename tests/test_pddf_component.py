"""Unit tests for sonic_platform_pddf/sonic_platform/component.py"""

import unittest
from unittest import mock

from tests.conftest import stub_sonic_platform_pddf_base, SONIC_PLATFORM_PDDF_DIR, load_module

stub_sonic_platform_pddf_base()
mod = load_module("pddf_component", SONIC_PLATFORM_PDDF_DIR / "component.py")
impl_mod = load_module("pddf_component_impl", SONIC_PLATFORM_PDDF_DIR / "impl_base" / "component.py")


class TestPddfComponent(unittest.TestCase):

    def _make(self, comp_type="BIOS", post_flash_reboot="cold"):
        c = mod.Component.__new__(mod.Component)
        c._get_attr = lambda key: {
            "type": comp_type,
            "post_flash_reboot": post_flash_reboot,
        }.get(key)
        c._impl = impl_mod.ComponentImplBase(c)
        return c

    def test_cold_reboot(self):
        msg = self._make(post_flash_reboot="cold").get_firmware_update_notification("img")
        self.assertIn("power reboot", msg)
        self.assertIn("BIOS", msg)

    def test_warm_reboot(self):
        msg = self._make(post_flash_reboot="warm").get_firmware_update_notification("img")
        self.assertIn("reboot device", msg)

    def test_fast_reboot(self):
        msg = self._make(post_flash_reboot="fast").get_firmware_update_notification("img")
        self.assertIn("fast reboot", msg)

    def test_none_post_flash(self):
        self.assertIsNone(self._make(post_flash_reboot=None).get_firmware_update_notification("img"))

    def test_none_string(self):
        self.assertIsNone(self._make(post_flash_reboot="none").get_firmware_update_notification("img"))

    def test_no_type(self):
        c = mod.Component.__new__(mod.Component)
        c._get_attr = lambda key: None
        c._impl = impl_mod.ComponentImplBase(c)
        self.assertIsNone(c.get_firmware_update_notification("img"))

    def test_invalid_raises(self):
        with self.assertRaises(RuntimeError):
            self._make(post_flash_reboot="invalid").get_firmware_update_notification("img")


class TestAvailableFirmwareVersion(unittest.TestCase):

    def _make(self, cmd, returncode=0, stdout=b""):
        c = mod.Component.__new__(mod.Component)
        c._get_cmd = lambda name: cmd if name == "available_version" else None
        c.get_name = lambda: "PSM-1"
        c.pddf_obj = mock.Mock()
        c.pddf_obj.get_cmd_output.return_value = mock.Mock(returncode=returncode, stdout=stdout)
        c._impl = impl_mod.ComponentImplBase(c)
        return c

    def test_available_version_cmd_output(self):
        c = self._make("tool available PSM-1", stdout=b"000SA006, 000PA001\n")
        self.assertEqual(c.get_available_firmware_version("img"), "000SA006, 000PA001")
        c.pddf_obj.get_cmd_output.assert_called_once_with("tool available PSM-1")

    def test_available_version_cmd_failure(self):
        c = self._make("tool available PSM-1", returncode=1)
        self.assertEqual(c.get_available_firmware_version("img"), "Unknown")

    def test_without_available_version_cmd(self):
        c = self._make(None)
        with mock.patch.object(impl_mod.PddfComponent, "get_available_firmware_version",
                               create=True, return_value="Unknown") as base:
            self.assertEqual(c.get_available_firmware_version("img"), "Unknown")
        base.assert_called_once_with(c, "img")
        c.pddf_obj.get_cmd_output.assert_not_called()


if __name__ == "__main__":
    unittest.main()
