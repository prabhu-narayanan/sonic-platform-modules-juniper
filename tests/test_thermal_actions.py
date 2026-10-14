"""Unit tests for sonic_platform/thermal_actions.py"""

import unittest
from unittest import mock
import sys
import types

from tests.conftest import (stub_sonic_platform_base, stub_sonic_py_common,
                            SONIC_PLATFORM_DIR, load_module)

stub_sonic_platform_base()
stub_sonic_py_common()

# Set up sonic_platform as a package
import sys, types
sp_pkg = types.ModuleType("sonic_platform")
sp_pkg.__path__ = [str(SONIC_PLATFORM_DIR)]
sys.modules.setdefault("sonic_platform", sp_pkg)

# Stub thermal_infos
thermal_infos_stub = types.ModuleType("sonic_platform.thermal_infos")


class FakeFanInfo:
    INFO_NAME = "fan_info"
    def __init__(self, fans=None):
        self._fans = fans or []
    def get_presence_fans(self):
        return self._fans


thermal_infos_stub.FanInfo = FakeFanInfo
sys.modules["sonic_platform.thermal_infos"] = thermal_infos_stub

mod = load_module("sonic_platform.thermal_actions", SONIC_PLATFORM_DIR / "thermal_actions.py",
                  package="sonic_platform")


class TestSetFanSpeedAction(unittest.TestCase):

    def test_default_speed(self):
        a = mod.SetFanSpeedAction()
        self.assertEqual(a.default_speed, 60)
        self.assertEqual(a.hightemp_speed, 100)

    def test_load_from_json_valid(self):
        a = mod.SetFanSpeedAction()
        a.load_from_json({"speed": "75"})
        self.assertEqual(a.speed, 75.0)

    def test_load_from_json_invalid_speed(self):
        a = mod.SetFanSpeedAction()
        with self.assertRaises(ValueError):
            a.load_from_json({"speed": "150"})

    def test_load_from_json_missing_speed(self):
        a = mod.SetFanSpeedAction()
        with self.assertRaises(ValueError):
            a.load_from_json({})

    def test_set_all_fan_speed(self):
        fan = mock.MagicMock()
        drawer = mock.MagicMock()
        drawer.get_all_fans.return_value = [fan]
        # Use the FanInfo class that the module actually imported
        FanInfo = sys.modules["sonic_platform.thermal_infos"].FanInfo
        info = FanInfo()
        info.get_presence_fans = lambda: [drawer]
        d = {FanInfo.INFO_NAME: info}
        mod.SetFanSpeedAction.set_all_fan_speed(d, 80)
        fan.set_speed.assert_called_once_with(80)


class TestSetAllFanSpeedAction(unittest.TestCase):

    def test_execute(self):
        a = mod.SetAllFanSpeedAction()
        a.speed = 50
        with mock.patch.object(mod.SetAllFanSpeedAction, "set_all_fan_speed") as m:
            a.execute({})
        m.assert_called_once_with({}, 50)


class TestThermalRecoverAction(unittest.TestCase):

    def test_load_from_json_valid(self):
        a = mod.ThermalRecoverAction()
        a.load_from_json({
            "default_speed": "25",
            "hightemp_speed": "100",
            "wait_interval": "240",
        })
        self.assertEqual(a.default_speed, 25.0)
        self.assertEqual(a.hightemp_speed, 100.0)
        self.assertEqual(a.wait_interval, 240)

    def test_load_from_json_missing_default_speed(self):
        a = mod.ThermalRecoverAction()
        with self.assertRaises(ValueError):
            a.load_from_json({"hightemp_speed": "100", "wait_interval": "240"})

    def test_load_from_json_missing_hightemp_speed(self):
        a = mod.ThermalRecoverAction()
        with self.assertRaises(ValueError):
            a.load_from_json({"default_speed": "25", "wait_interval": "240"})

    def test_load_from_json_invalid_default_speed(self):
        a = mod.ThermalRecoverAction()
        with self.assertRaises(ValueError):
            a.load_from_json({"default_speed": "-5", "hightemp_speed": "100", "wait_interval": "240"})


if __name__ == "__main__":
    unittest.main()
