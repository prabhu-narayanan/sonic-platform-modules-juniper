#!/usr/bin/env python3
#
# impl_base/current_sensor.py — default CurrentSensor platform implementation.
#
# Copyright (c) 2026, Juniper Networks, Inc.
# All rights reserved.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# The CurrentSensor facade selects a per-sensor backend from
# pddf-device.json (method=hwmon -> HwmonCurrentSensor, else the PDDF-based
# _JnprPddfCurrentSensor) and every method delegates to that backend.

import glob

try:
    from sonic_platform_pddf_base.pddf_current_sensor import PddfCurrentSensor
except ImportError as e:
    raise ImportError("%s - required module not found" % e)

try:
    from sonic_platform_base.sensor_base import CurrentSensorBase as _CurrentSensorBase
except ImportError:
    _CurrentSensorBase = None


def _is_hwmon_current_sensor(index, pddf_data):
    """Return True if CURRENT{N} in pddf-device.json uses method=hwmon."""
    if pddf_data is None:
        return False
    key = 'CURRENT{}'.format(index + 1)
    dev_attr = pddf_data.data.get(key, {}).get('dev_attr', {})
    return dev_attr.get('method') == 'hwmon'


class HwmonCurrentSensor(_CurrentSensorBase if _CurrentSensorBase else object):
    """Current rail read directly from a pmbus VRM's hwmon curr{N}_input.

    QFX5220 VRMs expose curr{N}_input (mA) via the generic Linux pmbus hwmon
    driver.  Each CURRENT{n} entry in pddf-device.json specifies:
      i2c.topo_info.parent_bus  — I2C bus number
      i2c.topo_info.dev_addr    — device address
      dev_attr.hwmon_attr       — sysfs attribute (e.g. curr2_input)
    Values are in mA.  No fixed thresholds (rail current is load-dependent).
    """

    def __init__(self, index, pddf_data=None, pddf_plugin_data=None):
        if _CurrentSensorBase:
            _CurrentSensorBase.__init__(self)
        key = 'CURRENT{}'.format(index + 1)
        obj = pddf_data.data.get(key, {}) if pddf_data is not None else {}
        da = obj.get('dev_attr', {})
        topo = obj.get('i2c', {}).get('topo_info', {})
        self._name = da.get('display_name', key)
        self._attr = da.get('hwmon_attr', 'curr1_input')
        self._da = da
        try:
            self._bus = int(topo.get('parent_bus', '0'), 0)
            self._addr = int(topo.get('dev_addr', '0'), 0)
        except (TypeError, ValueError):
            self._bus = self._addr = 0

    def get_name(self):
        return self._name

    def get_presence(self):
        return True

    def get_status(self):
        return True

    def get_model(self):
        return "N/A"

    def get_serial(self):
        return "N/A"

    def is_replaceable(self):
        return False

    def get_position_in_parent(self):
        return -1

    def _read(self, attr):
        pat = '/sys/bus/i2c/devices/{}-{:04x}/hwmon/hwmon*/{}'.format(
            self._bus, self._addr, attr)
        for p in glob.glob(pat):
            try:
                with open(p) as f:
                    return float(f.read().strip())
            except (OSError, ValueError):
                continue
        return None

    def get_value(self):
        """Rail current in mA."""
        v = self._read(self._attr)
        return round(v, 1) if v is not None else None

    def _thr(self, key):
        val = self._da.get(key)
        try:
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    def get_high_threshold(self):
        return self._thr('high_threshold')

    def get_low_threshold(self):
        return self._thr('low_threshold')

    def get_high_critical_threshold(self):
        return self._thr('crit_high_threshold')

    def get_low_critical_threshold(self):
        return self._thr('crit_low_threshold')


class _JnprPddfCurrentSensor(PddfCurrentSensor):
    """Juniper Current Sensor — thin wrapper over PddfCurrentSensor.

    Reads output current (I_OUT) from VRM hwmon sysfs via PDDF framework.
    JSON key: CURRENT1..N, attr_name: current1_input → drv_attr_name: curr1_input.
    """

    def __init__(self, index, pddf_data=None, pddf_plugin_data=None):
        PddfCurrentSensor.__init__(self, index, pddf_data, pddf_plugin_data)


class CurrentSensorImplBase:
    """CurrentSensor inherited public API. The facade builds the per-sensor
    backend (self._host._backend) in __init__; every method delegates to it.
    """

    def __init__(self, host):
        self._host = host

    def get_name(self):
        return self._host._backend.get_name()

    def get_presence(self):
        return self._host._backend.get_presence()

    def get_model(self):
        return self._host._backend.get_model()

    def get_serial(self):
        return self._host._backend.get_serial()

    def get_revision(self):
        return self._host._backend.get_revision()

    def get_status(self):
        return self._host._backend.get_status()

    def get_position_in_parent(self):
        return self._host._backend.get_position_in_parent()

    def is_replaceable(self):
        return self._host._backend.is_replaceable()

    def get_value(self):
        return self._host._backend.get_value()

    def get_high_threshold(self):
        return self._host._backend.get_high_threshold()

    def get_low_threshold(self):
        return self._host._backend.get_low_threshold()

    def set_high_threshold(self, value):
        return self._host._backend.set_high_threshold(value)

    def set_low_threshold(self, value):
        return self._host._backend.set_low_threshold(value)

    def get_high_critical_threshold(self):
        return self._host._backend.get_high_critical_threshold()

    def get_low_critical_threshold(self):
        return self._host._backend.get_low_critical_threshold()

    def set_high_critical_threshold(self, value):
        return self._host._backend.set_high_critical_threshold(value)

    def set_low_critical_threshold(self, value):
        return self._host._backend.set_low_critical_threshold(value)

    def get_minimum_recorded(self):
        return self._host._backend.get_minimum_recorded()

    def get_maximum_recorded(self):
        return self._host._backend.get_maximum_recorded()
