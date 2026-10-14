"""Unit tests for sonic_platform/thermal_conditions.py"""

import unittest
from unittest import mock

from tests.conftest import (stub_sonic_platform_base, stub_sonic_py_common,
                            stub_swsscommon, SONIC_PLATFORM_DIR, load_module)

stub_sonic_platform_base()
stub_sonic_py_common()
stub_swsscommon()

# Set up sonic_platform as a package for relative imports
import sys, types
sp_pkg = types.ModuleType("sonic_platform")
sp_pkg.__path__ = [str(SONIC_PLATFORM_DIR)]
sys.modules.setdefault("sonic_platform", sp_pkg)

# Stub thermal_infos with proper classes before loading conditions
thermal_infos_stub = types.ModuleType("sonic_platform.thermal_infos")

class FakeInfoBase:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)

class FakeFanInfo(FakeInfoBase):
    INFO_NAME = "fan_info"
    def get_presence_fans(self): return getattr(self, "_presence", [])
    def get_absence_fans(self): return getattr(self, "_absence", [])
    def get_bad_fans(self): return getattr(self, "_bad", [])

class FakeThermalInfo(FakeInfoBase):
    INFO_NAME = "thermal_info"
    def is_over_high_critical_threshold(self): return getattr(self, "_over", False)

class FakePsuInfo(FakeInfoBase):
    INFO_NAME = "psu_info"
    def get_presence_psus(self): return getattr(self, "_presence", [])
    def get_absence_psus(self): return getattr(self, "_absence", [])

thermal_infos_stub.FanInfo = FakeFanInfo
thermal_infos_stub.ThermalInfo = FakeThermalInfo
thermal_infos_stub.PsuInfo = FakePsuInfo
sys.modules["sonic_platform.thermal_infos"] = thermal_infos_stub

mod = load_module("sonic_platform.thermal_conditions", SONIC_PLATFORM_DIR / "thermal_conditions.py",
                  package="sonic_platform")

# Ensure the module's lazy imports will get our fake classes
# by re-registering after load (load may have triggered imports)
sys.modules["sonic_platform.thermal_infos"] = thermal_infos_stub


class TestFanConditions(unittest.TestCase):

    def _get_FanInfo(self):
        return sys.modules["sonic_platform.thermal_infos"].FanInfo

    def test_any_fan_presence_class_exists(self):
        self.assertTrue(hasattr(mod, 'AnyFanPresenceCondition'))

    def test_any_fan_absence_class_exists(self):
        self.assertTrue(hasattr(mod, 'AnyFanAbsenceCondition'))

    def test_any_fan_bad_class_exists(self):
        self.assertTrue(hasattr(mod, 'AnyFanBadCondition'))

    def test_fan_condition_no_info(self):
        c = mod.AnyFanPresenceCondition()
        # is_match with empty dict should not raise
        result = c.is_match({})
        self.assertIsNotNone(result)
        self.assertFalse(c.is_match({}))


class TestThermalConditions(unittest.TestCase):

    def _get_ThermalInfo(self):
        return sys.modules["sonic_platform.thermal_infos"].ThermalInfo

    def test_over_high_critical(self):
        TI = self._get_ThermalInfo()
        info = TI()
        info.is_over_high_critical_threshold = lambda: True
        d = {TI.INFO_NAME: info}
        c = mod.ThermalOverHighCriticalCondition()
        self.assertTrue(c.is_match(d))

    def test_not_over_high_critical(self):
        TI = self._get_ThermalInfo()
        info = TI()
        info.is_over_high_critical_threshold = lambda: False
        d = {TI.INFO_NAME: info}
        c = mod.ThermalOverHighCriticalCondition()
        self.assertFalse(c.is_match(d))


class TestPsuConditions(unittest.TestCase):

    def _get_PsuInfo(self):
        return sys.modules["sonic_platform.thermal_infos"].PsuInfo

    def test_any_absence(self):
        PI = self._get_PsuInfo()
        info = PI()
        info.get_absence_psus = lambda: ["psu1"]
        info.get_presence_psus = lambda: ["psu2"]
        d = {PI.INFO_NAME: info}
        c = mod.AnyPsuAbsenceCondition()
        self.assertTrue(c.is_match(d))

    def test_no_absence(self):
        PI = self._get_PsuInfo()
        info = PI()
        info.get_absence_psus = lambda: []
        info.get_presence_psus = lambda: ["psu1", "psu2"]
        d = {PI.INFO_NAME: info}
        c = mod.AnyPsuAbsenceCondition()
        self.assertFalse(c.is_match(d))

    def test_all_absence(self):
        PI = self._get_PsuInfo()
        info = PI()
        info.get_absence_psus = lambda: ["psu1", "psu2"]
        info.get_presence_psus = lambda: []
        d = {PI.INFO_NAME: info}
        c = mod.AllPsuAbsenceCondition()
        self.assertTrue(c.is_match(d))

    def test_all_presence(self):
        PI = self._get_PsuInfo()
        info = PI()
        info.get_absence_psus = lambda: []
        info.get_presence_psus = lambda: ["psu1", "psu2"]
        d = {PI.INFO_NAME: info}
        c = mod.AllPsuPresenceCondition()
        self.assertTrue(c.is_match(d))


if __name__ == "__main__":
    unittest.main()
