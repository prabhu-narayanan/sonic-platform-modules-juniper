"""Unit tests for sonic_platform/psu.py"""

import unittest
from unittest import mock

from tests.conftest import (stub_sonic_platform_base,
                            stub_sonic_platform_pddf_base,
                            SONIC_PLATFORM_DIR, load_module, _ensure_module)

stub_sonic_platform_pddf_base()
_ensure_module("sonic_platform")
_ensure_module("sonic_platform.pmbus_raw", {"resolve_i2c_bus": lambda *_args: 7})
impl_mod = load_module("sp_psu_impl", SONIC_PLATFORM_DIR / "impl_base" / "psu.py")
_ensure_module("sonic_platform.override",
               {"load_impl": lambda kind, host=None: impl_mod.PsuImplBase(host)})
mod = load_module("sp_psu", SONIC_PLATFORM_DIR / "psu.py")


class TestPsu(unittest.TestCase):

    def _make(self):
        p = mod.Psu.__new__(mod.Psu)
        p.psu_index = 1
        p._eeprom_path = None
        p._serial_cache = None
        p._revision_cache = None
        p._model_cache = None
        p._pmbus_i2c_dir = None
        p._ideeprom_authoritative = False
        p._presence_gpio_label = ''
        p._presence_gpio_offset = 0
        p._presence_gpio_active = '1'
        p._presence_gpio_pin = None
        p._is_replaceable = True
        p._impl = impl_mod.PsuImplBase(p)
        return p

    def test_get_presence_no_gpio(self):
        p = self._make()
        # No GPIO configured — falls back to PddfPsu.get_presence()
        with mock.patch.object(mod.PddfPsu, 'get_presence', return_value=False,
                               create=True):
            self.assertFalse(p.get_presence())

    def test_get_revision_no_eeprom(self):
        p = self._make()
        p._eeprom_path = None
        with mock.patch.object(p, 'get_presence', return_value=True):
            self.assertEqual(p.get_revision(), 'N/A')

    def test_get_serial_not_present(self):
        p = self._make()
        with mock.patch.object(p, 'get_presence', return_value=False):
            self.assertEqual(p.get_serial(), 'N/A')

    def test_get_powergood_not_present(self):
        p = self._make()
        with mock.patch.object(p, 'get_presence', return_value=False):
            self.assertFalse(p.get_powergood_status())

    def test_get_powergood_good_voltage(self):
        p = self._make()
        with mock.patch.object(p, 'get_presence', return_value=True):
            # get_voltage is inherited from PddfPsu stub — add it dynamically
            p.get_voltage = mock.MagicMock(return_value=12.0)
            self.assertTrue(p.get_powergood_status())

    def test_get_powergood_zero_voltage(self):
        p = self._make()
        with mock.patch.object(p, 'get_presence', return_value=True):
            p.get_voltage = mock.MagicMock(return_value=0.0)
            self.assertFalse(p.get_powergood_status())

    def test_symbolic_eeprom_parent_uses_bus_resolver(self):
        data = mock.MagicMock()
        data.data = {
            'PSU1_EEPROM': {
                'i2c': {
                    'topo_info': {
                        'parent_bus': 'TMC_CH1',
                        'dev_addr': '0x50',
                    },
                    'dev_attr': {},
                },
            },
        }

        def init_psu(instance, index, *_args):
            instance.psu_index = index + 1

        with mock.patch.object(mod, 'resolve_i2c_bus', return_value=7) as resolver, \
            mock.patch.object(mod.PddfPsu, '__init__', side_effect=init_psu), \
                mock.patch.object(mod.os.path, 'isfile', return_value=False):
            mod.Psu(0, data, {})

        resolver.assert_called_once_with(data, 'TMC_CH1')


if __name__ == "__main__":
    unittest.main()
