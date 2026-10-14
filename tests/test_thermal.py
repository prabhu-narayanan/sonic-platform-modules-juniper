"""Unit tests for sonic_platform/thermal.py"""

import unittest
from unittest import mock
import os
import sys

from tests.conftest import (stub_sonic_platform_base, stub_sonic_platform_pddf_base, stub_sonic_py_common,
                            stub_swsscommon, SONIC_PLATFORM_DIR, load_module)

stub_sonic_platform_pddf_base()
stub_sonic_py_common()
stub_swsscommon()
mod = load_module("sp_thermal", SONIC_PLATFORM_DIR / "thermal.py")
record_mod = load_module("sp_temp_record", SONIC_PLATFORM_DIR / "impl_base" / "temp_record.py")
with mock.patch.dict(sys.modules, {"sonic_platform.impl_base.temp_record": record_mod}):
    impl_mod = load_module("sp_thermal_impl", SONIC_PLATFORM_DIR / "impl_base" / "thermal.py")

# Sample thermal EM policy data:
# [NAME, I2C_ADDR, WTC, WT, HT, HTBF, YAT, YATBF, RAT, RATBF, FT]
SAMPLE_THERMAL_DATA = [
    ["Inlet Temp", 0x48, 30.0, 40.0, 75.0, 65.0, 85.0, 70.0, 95.0, 80.0, 105.0],
    ["Outlet Temp", 0x49, 35.0, 45.0, 80.0, 70.0, 90.0, 75.0, 100.0, 85.0, 110.0],
]
SAMPLE_OPTIC_DATA = [
    ["Optic", 0x00, 25.0, 35.0, 70.0, 60.0, 80.0, 65.0, 90.0, 75.0, 100.0],
]


class TestThermal(unittest.TestCase):

    def _make_thermal_obj(self, dev_attr=None):
        """Build a mock thermal_obj with i2c.dev_attr populated."""
        obj = mock.MagicMock()
        obj.__getitem__ = mock.MagicMock(side_effect=lambda k: {
            'i2c': {'dev_attr': dev_attr or {}}
        }[k])
        return obj

    def _make(self, dev_attr=None, is_psu=False, psu_index=0):
        t = mod.Thermal.__new__(mod.Thermal)
        t.thermal_obj = self._make_thermal_obj(dev_attr)
        t.thermal_obj_name = "Sensor"
        t.is_psu_thermal = is_psu
        t.thermals_psu_index = psu_index
        t.thermal_index = 1
        t._impl = impl_mod.ThermalImplBase(t)
        return t

    def test_get_name_psu(self):
        t = self._make(is_psu=True, psu_index=2)
        self.assertEqual(t.get_name(), "PSU2_TEMP1")

    def test_get_name_from_dev_attr(self):
        t = self._make(dev_attr={'display_name': 'Inlet Temp'})
        t.thermal_obj.__getitem__ = mock.MagicMock(
            side_effect=lambda k: {'i2c': {'dev_attr': {'display_name': 'Inlet Temp'}}}[k])
        self.assertEqual(t.get_name(), 'Inlet Temp')

    def test_get_name_fallback(self):
        t = self._make()
        # thermal_obj raises KeyError — falls back to thermal_obj_name
        t.thermal_obj.__getitem__ = mock.MagicMock(side_effect=KeyError)
        self.assertEqual(t.get_name(), 'Sensor')

    def test_get_high_threshold_from_json(self):
        t = self._make(dev_attr={'high_threshold': '75.0'})
        t.thermal_obj.__getitem__ = mock.MagicMock(
            side_effect=lambda k: {'i2c': {'dev_attr': {'high_threshold': '75.0'}}}[k])
        self.assertEqual(t.get_high_threshold(), 75.0)

    def test_get_high_threshold_missing(self):
        t = self._make(dev_attr={})
        t.thermal_obj.__getitem__ = mock.MagicMock(
            side_effect=lambda k: {'i2c': {'dev_attr': {}}}[k])
        self.assertIsNone(t.get_high_threshold())

    def test_get_WTC(self):
        t = self._make()
        t.thermal_obj.__getitem__ = mock.MagicMock(
            side_effect=lambda k: {'i2c': {'dev_attr': {'wtc': '30.0'}}}[k])
        self.assertEqual(t.get_WTC(), 30.0)

    def test_get_WT(self):
        t = self._make()
        t.thermal_obj.__getitem__ = mock.MagicMock(
            side_effect=lambda k: {'i2c': {'dev_attr': {'wt': '40.0'}}}[k])
        self.assertEqual(t.get_WT(), 40.0)

    def test_get_YAT(self):
        t = self._make()
        t.thermal_obj.__getitem__ = mock.MagicMock(
            side_effect=lambda k: {'i2c': {'dev_attr': {'yat': '85.0'}}}[k])
        self.assertEqual(t.get_YAT(), 85.0)

    def test_get_YATBF(self):
        t = self._make()
        t.thermal_obj.__getitem__ = mock.MagicMock(
            side_effect=lambda k: {'i2c': {'dev_attr': {'yat_bad_fan': '70.0'}}}[k])
        self.assertEqual(t.get_YATBF(), 70.0)

    def test_get_RAT(self):
        t = self._make()
        t.thermal_obj.__getitem__ = mock.MagicMock(
            side_effect=lambda k: {'i2c': {'dev_attr': {'rat': '95.0'}}}[k])
        self.assertEqual(t.get_RAT(), 95.0)

    def test_get_RATBF(self):
        t = self._make()
        t.thermal_obj.__getitem__ = mock.MagicMock(
            side_effect=lambda k: {'i2c': {'dev_attr': {'rat_bad_fan': '80.0'}}}[k])
        self.assertEqual(t.get_RATBF(), 80.0)

    def test_get_FT(self):
        t = self._make()
        t.thermal_obj.__getitem__ = mock.MagicMock(
            side_effect=lambda k: {'i2c': {'dev_attr': {'fire_threshold': '105.0'}}}[k])
        self.assertEqual(t.get_FT(), 105.0)

    def test_get_high_threshold_bad_fan(self):
        t = self._make()
        t.thermal_obj.__getitem__ = mock.MagicMock(
            side_effect=lambda k: {'i2c': {'dev_attr': {'high_threshold_bad_fan': '65.0'}}}[k])
        self.assertEqual(t.get_high_threshold_bad_fan(), 65.0)

    def test_get_dev_attr_missing_key_returns_none(self):
        t = self._make()
        t.thermal_obj.__getitem__ = mock.MagicMock(
            side_effect=lambda k: {'i2c': {'dev_attr': {}}}[k])
        self.assertIsNone(t._get_dev_attr('nonexistent'))

    def test_get_dev_attr_default(self):
        t = self._make()
        t.thermal_obj.__getitem__ = mock.MagicMock(
            side_effect=lambda k: {'i2c': {'dev_attr': {}}}[k])
        self.assertEqual(t._get_dev_attr('nonexistent', 99.0), 99.0)


if __name__ == "__main__":
    unittest.main()
