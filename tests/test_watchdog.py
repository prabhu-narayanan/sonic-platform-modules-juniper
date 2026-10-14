"""Unit tests for sonic_platform/watchdog.py"""

import unittest

from tests.conftest import stub_sonic_platform_base, stub_sonic_platform_pddf_base, stub_sonic_py_common, SONIC_PLATFORM_DIR, load_module

stub_sonic_platform_pddf_base()
stub_sonic_py_common()
mod = load_module("sp_watchdog", SONIC_PLATFORM_DIR / "watchdog.py")


class TestWatchdog(unittest.TestCase):

    def test_class_exists(self):
        self.assertTrue(hasattr(mod, 'Watchdog'))

    def test_inherits_pddf_watchdog(self):
        import sys
        pddf_watchdog_mod = sys.modules.get('sonic_platform_pddf_base.pddf_watchdog')
        self.assertIsNotNone(pddf_watchdog_mod)
        PddfWatchdog = pddf_watchdog_mod.PddfWatchdog
        self.assertTrue(issubclass(mod.Watchdog, PddfWatchdog))

if __name__ == "__main__":
    unittest.main()
