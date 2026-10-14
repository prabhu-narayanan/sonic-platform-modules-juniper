"""Unit tests for sonic_platform/sensor.py"""

import unittest
from unittest import mock

from tests.conftest import stub_sonic_platform_base, stub_syslog, SONIC_PLATFORM_DIR, load_module

stub_syslog()
stub_sonic_platform_base()
mod = load_module("sp_sensor", SONIC_PLATFORM_DIR / "sensor.py")
impl_mod = load_module("sp_sensor_impl", SONIC_PLATFORM_DIR / "impl_base" / "sensor.py")

# Sample voltage sensor data:
# [NAME, HIGH_TH, LOW_TH, HIGH_CRIT, LOW_CRIT, I2C_ADDR, LABEL, MULTI_FACTOR]
SAMPLE_DATA = [
    ["1.0V Rail", 1100, 900, 1200, 800, 0x40, "in1", 1],
    ["3.3V Rail", 3500, 3100, 3600, 3000, 0x41, "in2", 1],
]


class TestVoltageSensor(unittest.TestCase):

    def _make(self, idx=0):
        s = mod.VoltageSensor.__new__(mod.VoltageSensor)
        s.sensor_index = idx
        s.VOLTAGE_SENSORS = SAMPLE_DATA
        s._impl = impl_mod.SensorImplBase(s)
        return s

    def test_get_name(self):
        s = self._make(0)
        self.assertEqual(s.get_name(), "1.0V Rail")

    def test_get_high_threshold(self):
        s = self._make(0)
        self.assertEqual(s.get_high_threshold(), 1100)

    def test_get_low_threshold(self):
        s = self._make(0)
        self.assertEqual(s.get_low_threshold(), 900)

    def test_get_high_critical_threshold(self):
        s = self._make(0)
        self.assertEqual(s.get_high_critical_threshold(), 1200)

    def test_get_low_critical_threshold(self):
        s = self._make(0)
        self.assertEqual(s.get_low_critical_threshold(), 800)

    def test_set_high_threshold_raises(self):
        s = self._make(0)
        with self.assertRaises(NotImplementedError):
            s.set_high_threshold(1000)

    def test_set_low_threshold_raises(self):
        s = self._make(0)
        with self.assertRaises(NotImplementedError):
            s.set_low_threshold(500)

    def test_get_minimum_recorded(self):
        s = self._make(0)
        self.assertEqual(s.get_minimum_recorded(), 10.4)

    def test_get_maximum_recorded(self):
        s = self._make(0)
        self.assertEqual(s.get_maximum_recorded(), 25.0)

    def test_get_presence(self):
        s = self._make(0)
        self.assertTrue(s.get_presence())

    def test_get_status(self):
        s = self._make(0)
        self.assertTrue(s.get_status())

    def test_get_model(self):
        s = self._make(0)
        self.assertEqual(s.get_model(), "NA")

    def test_get_serial(self):
        s = self._make(0)
        self.assertEqual(s.get_serial(), "NA")

    def test_is_replaceable(self):
        s = self._make(0)
        self.assertFalse(s.is_replaceable())

    def test_get_position_in_parent(self):
        s = self._make(1)
        self.assertEqual(s.get_position_in_parent(), 1)

    def test_get_revision(self):
        s = self._make(0)
        self.assertEqual(s.get_revision(), "NA")


if __name__ == "__main__":
    unittest.main()
