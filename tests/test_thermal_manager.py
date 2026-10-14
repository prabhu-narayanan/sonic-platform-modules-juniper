"""Unit tests for sonic_platform/thermal_manager.py"""

import unittest
from unittest import mock
import sys
import types

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

# Stub the relative imports (.thermal_actions, .thermal_conditions, .thermal_infos)
for rel in ("sonic_platform.thermal_actions", "sonic_platform.thermal_conditions",
            "sonic_platform.thermal_infos"):
    sys.modules.setdefault(rel, types.ModuleType(rel))

mod = load_module("sonic_platform.thermal_manager", SONIC_PLATFORM_DIR / "thermal_manager.py",
                  package="sonic_platform")


class TestThermalManager(unittest.TestCase):

    def test_get_interval_default(self):
        """get_interval() returns _DEFAULT_INTERVAL (15) when JSON file absent."""
        mod.ThermalManager._interval = None
        with mock.patch('builtins.open', side_effect=FileNotFoundError):
            interval = mod.ThermalManager.get_interval()
        self.assertEqual(interval, 15)

    def test_get_interval_from_json(self):
        """get_interval() reads thermald_interval from THERMAL_CTRL.dev_attr."""
        mod.ThermalManager._interval = None
        fake_json = '{"THERMAL_CTRL": {"dev_attr": {"thermald_interval": 30}}}'
        with mock.patch('builtins.open', mock.mock_open(read_data=fake_json)):
            interval = mod.ThermalManager.get_interval()
        self.assertEqual(interval, 30)
        mod.ThermalManager._interval = None  # cleanup

    def test_get_interval_cached(self):
        """get_interval() returns cached value without re-reading file."""
        mod.ThermalManager._interval = 42
        interval = mod.ThermalManager.get_interval()
        self.assertEqual(interval, 42)
        mod.ThermalManager._interval = None  # cleanup


if __name__ == "__main__":
    unittest.main()
