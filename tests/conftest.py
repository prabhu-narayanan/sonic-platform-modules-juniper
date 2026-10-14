"""Shared test helpers and stubs for broadcom sonic-platform-modules-juniper tests.

Provides:
    - BASE_DIR, SONIC_PLATFORM_DIR, SONIC_PLATFORM_PDDF_DIR path constants
    - load_module() — import a .py file by path as a named module
    - Stub installers for sonic_platform_base, sonic_platform_pddf_base,
      sonic_py_common, sonic_eeprom, swsscommon, juniper.* etc.
"""

import importlib.util
import sys
import types
from pathlib import Path
from unittest import mock

BASE_DIR = Path(__file__).resolve().parent.parent
SONIC_PLATFORM_DIR = BASE_DIR / "sonic_platform"
# sonic_platform_pddf is now the same package as sonic_platform (PDDF_DIR = .)
SONIC_PLATFORM_PDDF_DIR = SONIC_PLATFORM_DIR
QFX5140_UTILS_DIR = BASE_DIR / "qfx5140" / "utils"
QFX5230_UTILS_DIR = BASE_DIR / "qfx5230" / "utils"
UTILS_DIR = BASE_DIR / "utils"


def load_module(name, path, package=None):
    """Import a Python file as a module by absolute path.
    
    If package is given, set __package__ to support relative imports.
    """
    path = Path(path)
    spec = importlib.util.spec_from_file_location(name, str(path),
                                                   submodule_search_locations=[])
    mod = importlib.util.module_from_spec(spec)
    if package:
        mod.__package__ = package
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Stub helpers — call these before importing modules that need them
# ---------------------------------------------------------------------------

def _ensure_module(name, attrs=None):
    """Create a stub module if it doesn't already exist in sys.modules."""
    if name not in sys.modules:
        sys.modules[name] = types.ModuleType(name)
    m = sys.modules[name]
    for k, v in (attrs or {}).items():
        if not hasattr(m, k):
            setattr(m, k, v)
    return m


def stub_sonic_platform_base():
    """Stub sonic_platform_base and its submodules with mock base classes."""
    # Base classes
    FanBase = type("FanBase", (), {
        "__init__": lambda self: None,
        "FAN_DIRECTION_INTAKE": "intake",
        "FAN_DIRECTION_EXHAUST": "exhaust",
        "STATUS_LED_COLOR_GREEN": "green",
        "STATUS_LED_COLOR_RED": "red",
        "STATUS_LED_COLOR_OFF": "off",
    })
    FanDrawerBase = type("FanDrawerBase", (), {"__init__": lambda self: None})
    PsuBase = type("PsuBase", (), {"__init__": lambda self: None})
    ThermalBase = type("ThermalBase", (), {"__init__": lambda self: None})
    ChassisBase = type("ChassisBase", (), {"__init__": lambda self: None})
    SfpBase = type("SfpBase", (), {"__init__": lambda self: None})
    PlatformBase = type("PlatformBase", (), {"__init__": lambda self: None})
    ComponentBase = type("ComponentBase", (), {"__init__": lambda self: None})
    WatchdogBase = type("WatchdogBase", (), {"__init__": lambda self: None})
    VoltageSensorBase = type("VoltageSensorBase", (), {"__init__": lambda self: None})
    SfpOptoeBase = type("SfpOptoeBase", (), {"__init__": lambda self: None})

    ThermalPolicyActionBase = type("ThermalPolicyActionBase", (), {"__init__": lambda self: None})
    ThermalPolicyConditionBase = type("ThermalPolicyConditionBase", (), {"__init__": lambda self: None})
    ThermalManagerBase = type("ThermalManagerBase", (), {"__init__": lambda self: None})
    ThermalInfoBase = type("ThermalInfoBase", (), {"__init__": lambda self: None})

    def thermal_json_object(name):
        """No-op decorator stub."""
        def decorator(cls):
            return cls
        return decorator

    _ensure_module("sonic_platform_base")
    _ensure_module("sonic_platform_base.fan_base", {"FanBase": FanBase})
    _ensure_module("sonic_platform_base.fan_drawer_base", {"FanDrawerBase": FanDrawerBase})
    _ensure_module("sonic_platform_base.psu_base", {"PsuBase": PsuBase})
    _ensure_module("sonic_platform_base.thermal_base", {"ThermalBase": ThermalBase})
    _ensure_module("sonic_platform_base.chassis_base", {"ChassisBase": ChassisBase})
    _ensure_module("sonic_platform_base.sfp_base", {"SfpBase": SfpBase})
    _ensure_module("sonic_platform_base.platform_base", {"PlatformBase": PlatformBase})
    _ensure_module("sonic_platform_base.component_base", {"ComponentBase": ComponentBase})
    _ensure_module("sonic_platform_base.watchdog_base", {"WatchdogBase": WatchdogBase})
    _ensure_module("sonic_platform_base.sensor_base", {"VoltageSensorBase": VoltageSensorBase})
    _ensure_module("sonic_platform_base.sonic_xcvr")
    _ensure_module("sonic_platform_base.sonic_xcvr.sfp_optoe_base", {"SfpOptoeBase": SfpOptoeBase})
    _ensure_module("sonic_platform_base.sonic_thermal_control")
    _ensure_module("sonic_platform_base.sonic_thermal_control.thermal_action_base",
                   {"ThermalPolicyActionBase": ThermalPolicyActionBase})
    _ensure_module("sonic_platform_base.sonic_thermal_control.thermal_condition_base",
                   {"ThermalPolicyConditionBase": ThermalPolicyConditionBase})
    _ensure_module("sonic_platform_base.sonic_thermal_control.thermal_json_object",
                   {"thermal_json_object": thermal_json_object})
    _ensure_module("sonic_platform_base.sonic_thermal_control.thermal_manager_base",
                   {"ThermalManagerBase": ThermalManagerBase})
    _ensure_module("sonic_platform_base.sonic_thermal_control.thermal_info_base",
                   {"ThermalPolicyInfoBase": ThermalInfoBase})


def stub_sonic_platform_pddf_base():
    """Stub sonic_platform_pddf_base with mock PDDF base classes."""
    stub_sonic_platform_base()

    PddfChassis = type("PddfChassis", (), {"__init__": lambda self, *a, **kw: None})
    PddfPsu = type("PddfPsu", (), {"__init__": lambda self, *a, **kw: None})
    PddfThermal = type("PddfThermal", (), {"__init__": lambda self, *a, **kw: None})
    PddfComponent = type("PddfComponent", (), {
        "__init__": lambda self, *a, **kw: None,
        "_get_attr": lambda self, key: None,
    })
    PddfEeprom = type("PddfEeprom", (), {"__init__": lambda self, *a, **kw: None})
    PddfPlatform = type("PddfPlatform", (), {"__init__": lambda self, *a, **kw: None})
    PddfWatchdog = type("PddfWatchdog", (), {"__init__": lambda self, *a, **kw: None})
    PddfFanDrawer = type("PddfFanDrawer", (), {"__init__": lambda self, *a, **kw: None})
    _FanBase = sys.modules.get("sonic_platform_base.fan_base").FanBase
    PddfFan = type("PddfFan", (_FanBase,), {
        "__init__": lambda self, *a, **kw: None,
        "get_presence": lambda self: False,
    })
    PddfVoltageSensor = type("PddfVoltageSensor", (), {"__init__": lambda self, *a, **kw: None})
    PddfCurrentSensor = type("PddfCurrentSensor", (), {"__init__": lambda self, *a, **kw: None})

    _ensure_module("sonic_platform_pddf_base")
    _ensure_module("sonic_platform_pddf_base.pddf_chassis", {"PddfChassis": PddfChassis})
    _ensure_module("sonic_platform_pddf_base.pddf_psu", {"PddfPsu": PddfPsu})
    _ensure_module("sonic_platform_pddf_base.pddf_thermal", {"PddfThermal": PddfThermal})
    _ensure_module("sonic_platform_pddf_base.pddf_component", {"PddfComponent": PddfComponent})
    _ensure_module("sonic_platform_pddf_base.pddf_eeprom", {"PddfEeprom": PddfEeprom})
    _ensure_module("sonic_platform_pddf_base.pddf_platform", {"PddfPlatform": PddfPlatform})
    _ensure_module("sonic_platform_pddf_base.pddf_watchdog", {"PddfWatchdog": PddfWatchdog})
    _ensure_module("sonic_platform_pddf_base.pddf_fan_drawer", {"PddfFanDrawer": PddfFanDrawer})
    _ensure_module("sonic_platform_pddf_base.pddf_fan", {"PddfFan": PddfFan})
    _ensure_module("sonic_platform_pddf_base.pddf_voltage_sensor", {"PddfVoltageSensor": PddfVoltageSensor})
    _ensure_module("sonic_platform_pddf_base.pddf_current_sensor", {"PddfCurrentSensor": PddfCurrentSensor})


def stub_sonic_py_common():
    """Stub sonic_py_common and its submodules."""
    logger_cls = type("Logger", (), {
        "__init__": lambda self, *a: None,
        "set_min_log_priority_info": lambda self: None,
        "set_min_log_priority_warning": lambda self: None,
        "log_info": lambda self, msg: None,
        "log_error": lambda self, msg: None,
        "log_warning": lambda self, msg: None,
        "log_debug": lambda self, msg: None,
        "log_notice": lambda self, msg: None,
        "log_critical": lambda self, msg: None,
    })
    _ensure_module("sonic_py_common", {"device_info": mock.MagicMock(), "logger": mock.MagicMock()})
    sys.modules["sonic_py_common"].logger = types.ModuleType("sonic_py_common.logger")
    sys.modules["sonic_py_common"].logger.Logger = logger_cls
    sys.modules["sonic_py_common.logger"] = sys.modules["sonic_py_common"].logger
    _ensure_module("sonic_py_common.general", {"getstatusoutput_noshell": mock.MagicMock(return_value=(0, ""))})
    _ensure_module("sonic_py_common.daemon_base", {"DaemonBase": type("DaemonBase", (), {"__init__": lambda self, *a: None})})


def stub_swsscommon():
    """Stub swsscommon."""
    SonicV2Connector = mock.MagicMock
    _ensure_module("swsscommon")
    _ensure_module("swsscommon.swsscommon", {"SonicV2Connector": SonicV2Connector})


def stub_sonic_eeprom():
    """Stub sonic_eeprom."""
    TlvInfoDecoder = type("TlvInfoDecoder", (), {
        "__init__": lambda self, *a, **kw: None,
        "_TLV_INFO_HDR_LEN": 11,
        "_TLV_CODE_SERIAL_NUMBER": 0x23,
        "_TLV_CODE_MAC_BASE": 0x24,
        "_TLV_CODE_PRODUCT_NAME": 0x21,
        "_TLV_CODE_PART_NUMBER": 0x22,
        "_TLV_CODE_SERVICE_TAG": 0x2F,
        "_TLV_CODE_DEVICE_VERSION": 0x26,
        "_TLV_CODE_VENDOR_EXT": 0xFD,
        "_TLV_CODE_CRC_32": 0xFE,
        "read_eeprom": lambda self: b"",
        "is_valid_tlvinfo_header": lambda self, data: False,
        "is_valid_tlv": lambda self, data: False,
        "decoder": lambda self, *a: ("", ""),
        "get_tlv_field": lambda self, data, code: (False, None),
    })
    _ensure_module("sonic_eeprom")
    _ensure_module("sonic_eeprom.eeprom_tlvinfo", {"TlvInfoDecoder": TlvInfoDecoder})


def stub_juniper():
    """Stub juniper.utils.utils and juniper.core.platform."""
    _ensure_module("juniper")
    _ensure_module("juniper.utils")
    _ensure_module("juniper.utils.utils", {
        "log_os_system": mock.MagicMock(return_value=(0, "")),
        "run_cmd": mock.MagicMock(return_value=(0, "")),
    })
    _ensure_module("juniper.core")
    _ensure_module("juniper.core.platform", {
        "getPlatform": mock.MagicMock(),
    })


def stub_syslog():
    """Stub syslog module."""
    _ensure_module("syslog", {
        "openlog": mock.MagicMock(),
        "syslog": mock.MagicMock(),
        "closelog": mock.MagicMock(),
        "LOG_ERR": 3,
        "LOG_INFO": 6,
        "LOG_WARNING": 4,
    })


def stub_all():
    """Install all stubs needed for most test modules."""
    stub_syslog()
    stub_sonic_platform_base()
    stub_sonic_platform_pddf_base()
    stub_sonic_py_common()
    stub_swsscommon()
    stub_sonic_eeprom()
    stub_juniper()
