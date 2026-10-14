"""Unit tests for sonic_platform/eeprom.py — compile/constant verification."""

import unittest
from unittest import mock

from tests.conftest import stub_sonic_eeprom, stub_sonic_platform_pddf_base, SONIC_PLATFORM_DIR, load_module

stub_sonic_platform_pddf_base()
stub_sonic_eeprom()
mod = load_module("sp_eeprom", SONIC_PLATFORM_DIR / "eeprom.py")


class TestEepromConstants(unittest.TestCase):

    def test_cache_file(self):
        self.assertEqual(mod.CACHE_FILE, "/var/run/platform_cache/onie_syseeprom.cache")

    def test_platform_cache_dir(self):
        self.assertEqual(mod.PLATFORM_CACHE_DIR, "/var/run/platform_cache")

    def test_class_exists(self):
        self.assertTrue(hasattr(mod, 'Eeprom'))

    def test_eeprom_inherits_pddf_eeprom(self):
        import sys
        pddf_eeprom_mod = sys.modules.get('sonic_platform_pddf_base.pddf_eeprom')
        self.assertIsNotNone(pddf_eeprom_mod)
        PddfEeprom = pddf_eeprom_mod.PddfEeprom
        self.assertTrue(issubclass(mod.Eeprom, PddfEeprom))

    def test_pddf_cache_root(self):
        self.assertEqual(mod.PDDF_CACHE_ROOT, '/var/cache/sonic/decode-syseeprom')


if __name__ == "__main__":
    unittest.main()
