"""Unit tests for sonic_platform/fan.py"""

import sys
import types
import unittest
from unittest import mock

from tests.conftest import stub_sonic_platform_base, stub_sonic_platform_pddf_base, stub_sonic_py_common, SONIC_PLATFORM_DIR, load_module

stub_sonic_platform_pddf_base()
stub_sonic_py_common()
mod = load_module("sp_fan", SONIC_PLATFORM_DIR / "fan.py")
impl_mod = load_module("sp_fan_impl", SONIC_PLATFORM_DIR / "impl_base" / "fan.py")


class TestFan(unittest.TestCase):

    def _make(self, fan_tray_index=0, fan_index=0):
        f = mod.Fan.__new__(mod.Fan)
        f._fan_tray_index = fan_tray_index
        f._fan_index = fan_index
        f._is_psu_fan = False
        f._psu_index = 0
        f._num_fantrays = 3
        f._fans_per_tray = 2
        f._fan_cfg = {}
        f._fan_start_idx = 0
        f._hwmon_fan_index = fan_tray_index * 2 + fan_index
        f._max_rpm = 23000
        f._min_rpm = 2500
        f._pwm_max = 255
        f._rpm_path = None
        f._pwm_path = None
        f._led_ok_path = None
        f._led_fail_path = None
        f._gpio_pin = None
        f._gpio_active_value = '1'
        f._plugin_data = None
        f._impl = impl_mod.FanImplBase(f)
        return f

    def test_get_serial(self):
        f = self._make()
        self.assertEqual(f.get_serial(), "N/A")

    def test_get_model(self):
        f = self._make()
        self.assertEqual(f.get_model(), "N/A")

    def test_get_presence(self):
        f = self._make()
        # No GPIO pin configured — should return False
        self.assertFalse(f.get_presence())

    def test_get_direction_exhaust(self):
        f = self._make()
        # No 'direction' in _fan_cfg — default is 'exhaust'
        self.assertEqual(f.get_direction(), f.FAN_DIRECTION_EXHAUST)

    def test_get_speed_tolerance(self):
        f = self._make()
        # No 'speed_tolerance' in _fan_cfg — default is '10'
        self.assertEqual(f.get_speed_tolerance(), 10)

    def test_set_status_led_no_paths(self):
        f = self._make()
        # _led_ok_path is None — returns False
        self.assertFalse(f.set_status_led("green"))

    def test_get_name_regular(self):
        f = self._make(fan_tray_index=1, fan_index=0)
        # No pddf_data — falls back to index-based name
        name = f.get_name()
        self.assertIsInstance(name, str)
        self.assertTrue(len(name) > 0)

    @mock.patch.object(impl_mod, "sysfs_write", return_value=True)
    @mock.patch.object(mod, "find_hwmon_by_name", return_value="/sys/class/hwmon/hwmon0")
    def test_set_speed_uses_shared_pwm(self, _find_hwmon, write):
        f = self._make(fan_tray_index=2, fan_index=1)
        f._fan_cfg = {"hwmon_name": "s32afc", "shared_pwm": "1"}

        self.assertTrue(f.set_speed(50))
        write.assert_called_once_with("/sys/class/hwmon/hwmon0/pwm1", 128)

    def test_get_name_psu_uses_one_based_psu_index(self):
        f = self._make(fan_index=0)
        f._is_psu_fan = True
        f._psu_index = 1
        self.assertEqual(f.get_name(), "PSU1_Fan1")

        f._psu_index = 2
        self.assertEqual(f.get_name(), "PSU2_Fan1")

    def test_get_position_in_parent(self):
        f = self._make(fan_index=0)
        self.assertEqual(f.get_position_in_parent(), 1)

    def test_get_position_in_parent_index1(self):
        f = self._make(fan_index=1)
        self.assertEqual(f.get_position_in_parent(), 2)

    def test_is_replaceable(self):
        f = self._make()
        self.assertTrue(f.is_replaceable())


if __name__ == "__main__":
    unittest.main()
