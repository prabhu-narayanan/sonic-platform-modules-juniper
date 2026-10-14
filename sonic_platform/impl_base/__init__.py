#!/usr/bin/env python3
#
# impl_base — default per-platform implementations ("impl" contract).
#
# Copyright (c) 2026, Juniper Networks, Inc.
# All rights reserved.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Each *ImplBase class holds ONLY the inherited (base-class) public API for a
# device type — the methods a platform may override. Non-inherited internals
# (construction, config parsing, state, and generic mechanics) live on the
# facade (sonic_platform.<kind>.<Kind>) and are reached from the impl via
# self._host; an internal helper belongs in an impl only when it is genuinely
# platform-divergent. Platforms subclass these in
# <platform>/pddf/platform_impl/<kind>.py and override only what differs.

from sonic_platform.impl_base.psu import PsuImplBase
from sonic_platform.impl_base.chassis import ChassisImplBase
from sonic_platform.impl_base.sfp import SfpImplBase
from sonic_platform.impl_base.temp_record import TemperatureRecordMixin
from sonic_platform.impl_base.thermal import ThermalImplBase
from sonic_platform.impl_base.fan import FanImplBase
from sonic_platform.impl_base.asic_thermal import AsicThermalImplBase
from sonic_platform.impl_base.sfp_thermal import SfpThermalImplBase
from sonic_platform.impl_base.fan_drawer import FanDrawerImplBase
from sonic_platform.impl_base.fwcomponent import FwComponentImplBase
from sonic_platform.impl_base.component import ComponentImplBase
from sonic_platform.impl_base.sensor import SensorImplBase
from sonic_platform.impl_base.watchdog import WatchdogImplBase
from sonic_platform.impl_base.voltage_sensor import VoltageSensorImplBase
from sonic_platform.impl_base.current_sensor import CurrentSensorImplBase

__all__ = ["PsuImplBase", "ChassisImplBase", "SfpImplBase", "ThermalImplBase",
           "FanImplBase", "AsicThermalImplBase", "SfpThermalImplBase",
           "FanDrawerImplBase", "FwComponentImplBase",
           "ComponentImplBase", "SensorImplBase",
           "WatchdogImplBase", "VoltageSensorImplBase", "CurrentSensorImplBase",
           "TemperatureRecordMixin"]
