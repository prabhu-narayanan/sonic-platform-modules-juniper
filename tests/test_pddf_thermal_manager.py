"""Unit tests for sonic_platform_pddf/sonic_platform/thermal_manager.py"""

import unittest
from unittest import mock
import sys
import types

from tests.conftest import (stub_sonic_platform_base, stub_sonic_py_common,
                            stub_swsscommon, stub_syslog,
                            SONIC_PLATFORM_PDDF_DIR, load_module)

stub_sonic_platform_base()
stub_sonic_py_common()
stub_swsscommon()
stub_syslog()

# Set up sonic_platform_pddf.sonic_platform as a package for relative imports
import sys, types
pddf_sp_pkg = types.ModuleType("sonic_platform_pddf.sonic_platform")
pddf_sp_pkg.__path__ = [str(SONIC_PLATFORM_PDDF_DIR)]
sys.modules.setdefault("sonic_platform_pddf", types.ModuleType("sonic_platform_pddf"))
sys.modules.setdefault("sonic_platform_pddf.sonic_platform", pddf_sp_pkg)

# Stub the relative imports from sonic_platform_pddf thermal modules
for rel in ("sonic_platform_pddf.sonic_platform.thermal_actions",
            "sonic_platform_pddf.sonic_platform.thermal_conditions",
            "sonic_platform_pddf.sonic_platform.thermal_infos"):
    sys.modules.setdefault(rel, types.ModuleType(rel))

mod = load_module("sonic_platform_pddf.sonic_platform.thermal_manager",
                  SONIC_PLATFORM_PDDF_DIR / "thermal_manager.py",
                  package="sonic_platform_pddf.sonic_platform")


class TestPddfThermalManager(unittest.TestCase):

    def setUp(self):
        mod.ThermalManager._interval = None

    def test_default_interval(self):
        with mock.patch("builtins.open", side_effect=FileNotFoundError):
            self.assertEqual(mod.ThermalManager.get_interval(), 15)

    def test_interval_from_json(self):
        import json
        data = {"THERMAL_CTRL": {"dev_attr": {"thermald_interval": "20"}}}
        m = mock.mock_open(read_data=json.dumps(data))
        with mock.patch("builtins.open", m):
            self.assertEqual(mod.ThermalManager.get_interval(), 20)

    def test_interval_cached(self):
        mod.ThermalManager._interval = 42
        self.assertEqual(mod.ThermalManager.get_interval(), 42)


if __name__ == "__main__":
    unittest.main()
