"""Unit tests for sonic_platform_pddf/sonic_platform/thermal.py"""

import unittest
import ast
import sys
import types
from unittest import mock

from tests.conftest import stub_sonic_platform_pddf_base, SONIC_PLATFORM_PDDF_DIR, load_module

stub_sonic_platform_pddf_base()
mod = load_module("pddf_thermal", SONIC_PLATFORM_PDDF_DIR / "thermal.py")
record_mod = load_module("pddf_temp_record", SONIC_PLATFORM_PDDF_DIR / "impl_base" / "temp_record.py")
with mock.patch.dict(sys.modules, {"sonic_platform.impl_base.temp_record": record_mod}):
    impl_mod = load_module("pddf_thermal_impl", SONIC_PLATFORM_PDDF_DIR / "impl_base" / "thermal.py")


class TestPddfThermal(unittest.TestCase):

    def _make(self, dev_attr=None, is_psu=False, psu_index=0):
        t = mod.Thermal.__new__(mod.Thermal)
        t.thermal_index = 1
        t.thermals_psu_index = psu_index
        t.is_psu_thermal = is_psu
        t.thermal_obj_name = "TEMP1"
        t.thermal_obj = {"i2c": {"dev_attr": dev_attr or {}}}
        t._impl = impl_mod.ThermalImplBase(t)
        return t

    def test_get_name_from_dev_attr(self):
        t = self._make(dev_attr={"display_name": "Inlet Temp"})
        self.assertEqual(t.get_name(), "Inlet Temp")

    def test_get_name_fallback(self):
        t = self._make()
        self.assertEqual(t.get_name(), "TEMP1")

    def test_get_name_psu(self):
        t = self._make(is_psu=True, psu_index=2)
        self.assertEqual(t.get_name(), "PSU2_TEMP1")

    def test_get_dev_attr(self):
        t = self._make(dev_attr={"wtc": "35.0", "wt": "40"})
        self.assertEqual(t._get_dev_attr("wtc"), 35.0)
        self.assertEqual(t._get_dev_attr("wt"), 40.0)
        self.assertIsNone(t._get_dev_attr("missing"))
        self.assertEqual(t._get_dev_attr("missing", 99.0), 99.0)

    def test_get_high_threshold(self):
        t = self._make(dev_attr={"high_threshold": "75"})
        self.assertEqual(t.get_high_threshold(), 75.0)

    def test_threshold_getters(self):
        attrs = {
            "wtc": "30", "wt": "40", "yat": "85", "yat_bad_fan": "70",
            "rat": "95", "rat_bad_fan": "80", "fire_threshold": "105",
            "high_threshold_bad_fan": "72",
        }
        t = self._make(dev_attr=attrs)
        self.assertEqual(t.get_WTC(), 30.0)
        self.assertEqual(t.get_WT(), 40.0)
        self.assertEqual(t.get_YAT(), 85.0)
        self.assertEqual(t.get_YATBF(), 70.0)
        self.assertEqual(t.get_RAT(), 95.0)
        self.assertEqual(t.get_RATBF(), 80.0)
        self.assertEqual(t.get_FT(), 105.0)
        self.assertEqual(t.get_high_threshold_bad_fan(), 72.0)

    def test_get_high_critical_from_json(self):
        t = self._make(dev_attr={"rat": "100"})
        self.assertEqual(t.get_high_critical_threshold(), 100.0)

    def test_get_high_critical_fallback(self):
        t = self._make()
        mod.PddfThermal.get_high_critical_threshold = mock.MagicMock(return_value=110.0)
        self.assertEqual(t.get_high_critical_threshold(), 110.0)


class TestChassisThermalEnumeration(unittest.TestCase):

    def test_optics_are_policy_only_and_copper_is_excluded(self):
        source = ast.parse((SONIC_PLATFORM_PDDF_DIR / "chassis.py").read_text())
        chassis_class = next(node for node in source.body
                             if isinstance(node, ast.ClassDef) and node.name == "Chassis")
        methods = [node for node in chassis_class.body
                   if isinstance(node, ast.FunctionDef) and node.name in
                   ("_init_sfp_thermals", "get_thermal_policy_thermals",
                    "get_all_sfps", "get_num_sfps")]
        class NullXcvrObject:
            pass

        optic_module = types.ModuleType("thermal_enumeration.sfp_thermal")
        optic_module.SfpThermal = mock.Mock(side_effect=lambda index, sfp, thresholds:
                                           types.SimpleNamespace(_port_index=index))
        namespace = {"__name__": "thermal_enumeration.chassis",
                     "__package__": "thermal_enumeration",
                     "NullXcvrObject": NullXcvrObject}
        exec(compile(ast.Module(body=methods, type_ignores=[]), "chassis.py", "exec"),
             namespace)
        board_thermals = [object() for index in range(11)]
        host = types.SimpleNamespace(
            _thermal_list=board_thermals,
            _sfp_list=[NullXcvrObject() for index in range(48)] +
                      [object() for index in range(6)],
            platform_inventory={"num_ports": 54},
            pddf_obj=types.SimpleNamespace(data={"OPTIC_THRESHOLDS": {}}),
            get_all_thermals=lambda: board_thermals)
        with mock.patch.dict(sys.modules, {"thermal_enumeration.sfp_thermal": optic_module}):
            namespace["_init_sfp_thermals"](host)
        self.assertEqual(len(host._thermal_list), 11)
        self.assertEqual([sensor._port_index for sensor in host._sfp_thermals],
                         list(range(48, 54)))
        policy_thermals = namespace["get_thermal_policy_thermals"](host)
        self.assertEqual(policy_thermals[:11], board_thermals)
        self.assertEqual(policy_thermals[11:], host._sfp_thermals)
        self.assertEqual(len(policy_thermals), 17)
        host.get_all_sfps = lambda: namespace["get_all_sfps"](host)
        self.assertEqual(host.get_all_sfps(), host._sfp_list[48:54])
        self.assertEqual(namespace["get_num_sfps"](host), 6)
        self.assertEqual(len(host._sfp_list), 54)


if __name__ == "__main__":
    unittest.main()
