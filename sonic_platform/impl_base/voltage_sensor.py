#!/usr/bin/env python3
#
# impl_base/voltage_sensor.py — default VoltageSensor platform implementation.
#
# Copyright (c) 2026, Juniper Networks, Inc.
# All rights reserved.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# The VoltageSensor facade selects a per-sensor backend from
# pddf-device.json (method=hwmon -> HwmonVoltageSensor, else the PDDF-based
# _JnprPddfVoltageSensor) and every method delegates to that backend. The
# PDDF backend stays a real PddfVoltageSensor subclass so the framework's
# _find_i2c_bus_by_adapter hook still works.

import glob

try:
    from sonic_platform_pddf_base.pddf_voltage_sensor import PddfVoltageSensor
    from sonic_platform.sysfs_util import find_i2c_bus_mux
except ImportError as e:
    raise ImportError("%s - required module not found" % e)

try:
    from sonic_platform_base.sensor_base import VoltageSensorBase as _VoltageSensorBase
except ImportError:
    _VoltageSensorBase = None


def _is_hwmon_voltage_sensor(index, pddf_data):
    """Return True if VOLTAGE{N} in pddf-device.json uses method=hwmon."""
    if pddf_data is None:
        return False
    key = 'VOLTAGE{}'.format(index + 1)
    dev_attr = pddf_data.data.get(key, {}).get('dev_attr', {})
    return dev_attr.get('method') == 'hwmon'


class HwmonVoltageSensor(_VoltageSensorBase if _VoltageSensorBase else object):
    """Voltage rail read directly from a pmbus VRM's hwmon inX_input.

    QFX5220 VRMs (pmbus regulators instantiated by qfx5220_platform_init.py)
    expose in{N}_input (mV) via the generic Linux pmbus hwmon driver.
    Each VOLTAGE{n} entry in pddf-device.json specifies:
      i2c.topo_info.parent_bus  — I2C bus number
      i2c.topo_info.dev_addr    — device address
      dev_attr.hwmon_attr       — sysfs attribute (e.g. in2_input)
    Values and thresholds are in mV.
    """

    def __init__(self, index, pddf_data=None, pddf_plugin_data=None):
        if _VoltageSensorBase:
            _VoltageSensorBase.__init__(self)
        key = 'VOLTAGE{}'.format(index + 1)
        obj = pddf_data.data.get(key, {}) if pddf_data is not None else {}
        da = obj.get('dev_attr', {})
        topo = obj.get('i2c', {}).get('topo_info', {})
        self._name = da.get('display_name', key)
        self._attr = da.get('hwmon_attr', 'in1_input')
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
        """Rail voltage in mV."""
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


class _JnprPddfVoltageSensor(PddfVoltageSensor):
    """Juniper Voltage Sensor — extends the PDDF base class.

    The base class reads volt1_input from sysfs but applies no scaling
    and ignores the JSON thresholds, so this subclass adds:
      - multi_factor/decimate_factor scaling of the raw sysfs value
      - thresholds from the VOLTAGE{N} dev_attr block
      - adapter name resolution via find_i2c_bus_mux, which handles
        multi-level MUX cascades (mux2_addr, mux2_chan)
    """

    def __init__(self, index, pddf_data=None, pddf_plugin_data=None):
        PddfVoltageSensor.__init__(self, index, pddf_data, pddf_plugin_data)

    # -------------------------------------------------------------- #
    #  JSON dev_attr threshold helpers                                #
    # -------------------------------------------------------------- #
    def _get_dev_attr(self, key, default=None):
        """Read a numeric value from VOLTAGE{N} dev_attr in JSON."""
        try:
            dev_attr = self.sensor_obj.get('dev_attr') or {}
            platform = self.pddf_obj.data.get('PLATFORM', {})
            if (not dev_attr and
                    platform.get('nested_voltage_dev_attr') == '1'):
                dev_attr = self.sensor_obj.get('i2c', {}).get('dev_attr', {})
            val = dev_attr.get(key)
            return float(val) if val is not None else default
        except (KeyError, TypeError, ValueError):
            return default

    def _get_scale_factor(self, key):
        """Positive scale factor from dev_attr, or None if absent/invalid."""
        val = self._get_dev_attr(key)
        if val is None or val <= 0:
            return None
        return val

    def get_value(self):
        """Rail voltage in mV, scaled by multi_factor and/or decimate_factor.

        Rails behind a resistor divider (or reported by the VRM on a
        different scale) read low in sysfs; the JSON dev_attr factors
        convert the raw sysfs value to the actual rail voltage. Either
        factor may appear on its own — the absent one defaults to 1, and
        with neither present the sysfs value is returned unmodified.
        """
        val = super().get_value()
        if val is None:
            return None
        multi_factor = self._get_scale_factor('multi_factor')
        decimate_factor = self._get_scale_factor('decimate_factor')
        if multi_factor is None and decimate_factor is None:
            return val
        if multi_factor is None:
            multi_factor = 1.0
        if decimate_factor is None:
            decimate_factor = 1.0
        return round(val * multi_factor / decimate_factor, 1)

    def get_high_threshold(self):
        """High voltage threshold from JSON dev_attr, falls back to PDDF base."""
        val = self._get_dev_attr('high_threshold')
        if val is not None:
            return val
        return super().get_high_threshold()

    def get_low_threshold(self):
        """Low voltage threshold from JSON dev_attr, falls back to PDDF base."""
        val = self._get_dev_attr('low_threshold')
        if val is not None:
            return val
        return super().get_low_threshold()

    def get_high_critical_threshold(self):
        """Critical high voltage threshold from JSON dev_attr.
        Falls back to high_threshold, then PDDF base.
        """
        val = self._get_dev_attr('crit_high_threshold')
        if val is not None:
            return val
        val = self._get_dev_attr('high_threshold')
        if val is not None:
            return val
        return super().get_high_critical_threshold()

    def get_low_critical_threshold(self):
        """Critical low voltage threshold from JSON dev_attr.
        Falls back to low_threshold, then PDDF base.
        """
        val = self._get_dev_attr('crit_low_threshold')
        if val is not None:
            return val
        val = self._get_dev_attr('low_threshold')
        if val is not None:
            return val
        return super().get_low_critical_threshold()

    @staticmethod
    def _find_i2c_bus_by_adapter(adapter_name, mux_chan=''):
        """Override base class with Juniper MUX bus resolution.

        find_i2c_bus_mux handles multi-level MUX cascades including
        mux2_addr/mux2_chan for platforms with cascaded I2C MUX topology.
        """
        return find_i2c_bus_mux(adapter_name, mux_chan)


class VoltageSensorImplBase:
    """VoltageSensor inherited public API. The facade builds the per-sensor
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
