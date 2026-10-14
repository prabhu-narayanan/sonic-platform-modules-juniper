"""Unit tests for sonic_platform_pddf/sonic_platform/voltage_sensor.py"""

import unittest
from unittest import mock
import sys
import types

from tests.conftest import stub_sonic_platform_pddf_base, SONIC_PLATFORM_PDDF_DIR, load_module

stub_sonic_platform_pddf_base()

# Stub sonic_platform.sysfs_util
sysfs_stub = types.ModuleType("sonic_platform.sysfs_util")
sysfs_stub.find_i2c_bus_mux = mock.MagicMock(return_value=66)
sys.modules["sonic_platform.sysfs_util"] = sysfs_stub
sys.modules.setdefault("sonic_platform", types.ModuleType("sonic_platform"))

mod = load_module("pddf_voltage_sensor", SONIC_PLATFORM_PDDF_DIR / "voltage_sensor.py")
impl_mod = load_module("pddf_voltage_sensor_impl", SONIC_PLATFORM_PDDF_DIR / "impl_base" / "voltage_sensor.py")


class TestVoltageSensor(unittest.TestCase):

    def test_find_i2c_bus_by_adapter_delegates(self):
        with mock.patch.object(impl_mod, "find_i2c_bus_mux", return_value=42):
            result = impl_mod._JnprPddfVoltageSensor._find_i2c_bus_by_adapter("i2c-supercon.2:1", "3")
        self.assertEqual(result, 42)

    def test_class_inherits_pddf(self):
        self.assertTrue(issubclass(impl_mod._JnprPddfVoltageSensor, impl_mod.PddfVoltageSensor))


if __name__ == "__main__":
    unittest.main()
