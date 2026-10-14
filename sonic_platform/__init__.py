# Juniper HPE Platform - sonic_platform module (PDDF)
# Generic platform support — all hardware config in pddf-device.json

__all__ = [
    "platform", "chassis", "component", "eeprom", "fan",
    "fan_drawer", "gpio_helper", "sysfs_util", "psu", "sfp",
    "thermal", "voltage_sensor", "thermal_manager",
    "thermal_conditions", "thermal_actions", "thermal_infos",
    # watchdog intentionally excluded: watchdog.py needs sonic_platform_pddf_base
    # which is not installed at package-import time on first boot.
    # Import directly: from sonic_platform.watchdog import Watchdog
]
from sonic_platform import *
