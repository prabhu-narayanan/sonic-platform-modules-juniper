#!/usr/bin/env python3
#
# liquid_cooling.py — leak / pressure / flow / humidity sensors (OE-L SKU)
#
# Sensors on the liquid-cooled QFX5250-64OE-L are read from ADS1015 ADCs and
# an HDC2010 via the kernel IIO subsystem, then converted to engineering units
# with a piecewise-linear sampling table.  Topology, tables and thresholds all
# come from pddf-device.json — there are no platform constants here, so a new
# platform only needs JSON entries.
#
# Conversion matches the Junos EVO reference implementation for the same
# hardware (cevo/hwd/common/sensor/src/Sensor.cpp: interpolateFromTable /
# interpolateLinear, tables from capdb qfx5250_64oe_l_fpc_fdt.h):
#   leak     score 0-100, INVERSE (low voltage = leak), thresholds yat/rat/ft
#   pressure mBar, thresholds lft/vlrat/lyat/hyat/vhrat/hft
#   humidity %RH, thresholds yat/rat/ft
#
# NOTE: the ADS1015 input range (PGA) must be set before these read correctly.
# qfx5250/utils/qfx5250_post_pddf_init.py:adc_pga_init() does that at boot.  At the
# driver default (+-2.048 V) the leak channels saturate at 2047 mV, which this
# table converts to a score of 22 — above the fire threshold of 20.
#
# Copyright (c) 2026, Juniper Networks, Inc.
# All rights reserved.

import glob
import os

try:
    from sonic_platform_base.sensor_base import SensorBase
    from sonic_platform_base.liquid_cooling_base import (
        LeakageSensorBase, LiquidCoolingBase)
except ImportError as e:
    raise ImportError("%s - required module not found" % e)


def _interpolate_linear(x, x1, y1, x2, y2):
    if x2 == x1:
        return float(y1)
    return y1 + (x - x1) * float(y2 - y1) / float(x2 - x1)


def interpolate_from_table(x_value, points):
    """Piecewise-linear lookup with extrapolation past both ends.

    Mirrors EVO Sensor::interpolateFromTable, including its truncation to int.
    Returns None when the table is unusable.
    """
    if not points or len(points) < 2:
        return None

    if len(points) == 2:
        (x1, y1), (x2, y2) = points[0], points[1]
        return int(_interpolate_linear(x_value, x1, y1, x2, y2))

    last = len(points) - 2
    for i in range(last + 1):
        x1, y1 = points[i]
        x2, y2 = points[i + 1]
        if ((x1 <= x_value <= x2)
                or (i == 0 and x_value < x1)
                or (i == last and x_value > x2)):
            return int(_interpolate_linear(x_value, x1, y1, x2, y2))
    return None


class _IioSensor(SensorBase):
    """Common IIO plumbing driven by a pddf-device.json entry.

    Reads i2c.topo_info for the device address, i2c.dev_attr for the display
    name, channel, sampling table, limits and thresholds.
    """

    def __init__(self, name, obj):
        SensorBase.__init__(self)
        self._key = name
        i2c = obj.get('i2c', {})
        self._da = i2c.get('dev_attr', {})
        topo = i2c.get('topo_info', {})
        self._name = self._da.get('display_name', name)
        try:
            self._addr = int(topo.get('dev_addr', '0'), 0)
        except (TypeError, ValueError):
            self._addr = 0
        self._chan = self._int_attr('channel', 0)
        self._points = self._table()
        self._min = self._int_attr('min_val')
        self._max = self._int_attr('max_val')
        self._iio_dir = None

    # -- config helpers -------------------------------------------------- #
    def _int_attr(self, key, default=None):
        try:
            val = self._da.get(key)
            return int(str(val), 0) if val is not None else default
        except (TypeError, ValueError):
            return default

    def _table(self):
        """sampling_points as [[x, y], ...] pairs from JSON."""
        pts = []
        for pair in self._da.get('sampling_points', []) or []:
            try:
                pts.append((int(pair[0]), int(pair[1])))
            except (TypeError, ValueError, IndexError):
                continue
        return pts

    # -- sysfs ----------------------------------------------------------- #
    def _find_iio_dir(self):
        if self._iio_dir and os.path.isdir(self._iio_dir):
            return self._iio_dir
        pattern = '/sys/bus/i2c/devices/*-{:04x}/iio:device*'.format(self._addr)
        for path in sorted(glob.glob(pattern)):
            self._iio_dir = path
            return path
        return None

    def _read_float(self, attr):
        iio = self._find_iio_dir()
        if not iio:
            return None
        try:
            with open(os.path.join(iio, attr)) as f:
                return float(f.read().strip())
        except (OSError, ValueError):
            return None

    def _read_millivolts(self):
        """Channel voltage in mV (raw * scale), or None if unreadable."""
        raw = self._read_float('in_voltage{}_raw'.format(self._chan))
        scale = self._read_float('in_voltage{}_scale'.format(self._chan))
        if raw is None or scale is None:
            return None
        return raw * scale

    def _clamp(self, value):
        if value is None:
            return None
        if self._min is not None:
            value = max(value, self._min)
        if self._max is not None:
            value = min(value, self._max)
        return value

    # -- SensorBase ------------------------------------------------------ #
    def get_name(self):
        return self._name

    def get_presence(self):
        return self._find_iio_dir() is not None

    def get_status(self):
        return self.get_value() is not None

    def is_replaceable(self):
        return False

    def get_position_in_parent(self):
        return self._int_attr('position', -1)

    def get_minimum_recorded(self):
        raise NotImplementedError

    def get_maximum_recorded(self):
        raise NotImplementedError


class LeakSensor(_IioSensor, LeakageSensorBase):
    """Leak detector: ADC voltage -> 0-100 leakage score (inverse).

    A dry loop sits high (~2800 mV -> score 0); score rises as voltage falls.
    """

    def __init__(self, name, obj):
        _IioSensor.__init__(self, name, obj)

    @classmethod
    def get_type(cls):
        return "SENSOR_TYPE_LEAKAGE"

    @classmethod
    def get_unit(cls):
        return "score"

    def get_value(self):
        """Leakage score 0-100, or None if the sensor cannot be read."""
        millivolts = self._read_millivolts()
        if millivolts is None:
            return None
        score = interpolate_from_table(int(millivolts), self._points)
        return self._clamp(score)

    def is_leak(self):
        """True when the score exceeds the yellow-alarm threshold."""
        score = self.get_value()
        if score is None:
            return False
        yat = self._int_attr('yat')
        return score > yat if yat is not None else score > 0

    def get_high_threshold(self):
        return self._int_attr('rat')

    def get_high_critical_threshold(self):
        return self._int_attr('ft')

    def get_low_threshold(self):
        return self._int_attr('yat')


class PressureSensor(_IioSensor):
    """Coolant pressure in mBar.

    Deliberately not clamped to min_val/max_val. The EVO capdb sets 300/1100
    for these sensors, yet its own thresholds run to hft=3250 mBar, so those
    bounds cannot be an output range — applying them would clip a genuine
    over-pressure reading down into the normal band. Their real meaning is
    unknown; they are left unapplied until the board team clarifies.
    """

    @classmethod
    def get_type(cls):
        return "SENSOR_TYPE_PRESSURE"

    @classmethod
    def get_unit(cls):
        return "mBar"

    def get_value(self):
        millivolts = self._read_millivolts()
        if millivolts is None:
            return None
        return interpolate_from_table(int(millivolts), self._points)

    def get_high_threshold(self):
        return self._int_attr('hyat')

    def get_low_threshold(self):
        return self._int_attr('lyat')

    def get_high_critical_threshold(self):
        return self._int_attr('vhrat')

    def get_low_critical_threshold(self):
        return self._int_attr('vlrat')

    def get_high_fire_threshold(self):
        return self._int_attr('hft')

    def get_low_fire_threshold(self):
        return self._int_attr('lft')


class FlowSensor(_IioSensor):
    """Coolant flow.

    Reported as raw millivolts: no mV-to-L/min transfer function is defined
    for this board in either the EVO capdb or SONiC.  Add sampling_points to
    the JSON entry once the board team supplies the curve and this starts
    returning engineering units with no code change.
    """

    @classmethod
    def get_type(cls):
        return "SENSOR_TYPE_FLOW"

    @classmethod
    def get_unit(cls):
        return "mV"

    def get_value(self):
        millivolts = self._read_millivolts()
        if millivolts is None:
            return None
        if self._points:
            return self._clamp(interpolate_from_table(int(millivolts),
                                                      self._points))
        return int(millivolts)


class HumiditySensor(_IioSensor):
    """Relative humidity (%) from an HDC2010."""

    @classmethod
    def get_type(cls):
        return "SENSOR_TYPE_HUMIDITY"

    @classmethod
    def get_unit(cls):
        return "%"

    def get_value(self):
        raw = self._read_float('in_humidityrelative_raw')
        scale = self._read_float('in_humidityrelative_scale')
        if raw is None or scale is None:
            return None
        return self._clamp(round(raw * scale / 1000.0, 2))

    def get_high_threshold(self):
        return self._int_attr('yat')

    def get_high_critical_threshold(self):
        return self._int_attr('rat')

    def get_fire_threshold(self):
        return self._int_attr('ft')


# device_type in pddf-device.json -> class
_SENSOR_CLASSES = {
    'LEAK_SENSOR': LeakSensor,
    'PRESSURE_SENSOR': PressureSensor,
    'FLOW_SENSOR': FlowSensor,
    'HUMIDITY_SENSOR': HumiditySensor,
}


class LiquidCooling(LiquidCoolingBase):
    """Liquid cooling subsystem built from pddf-device.json.

    Absent on air-cooled SKUs, whose JSON carries none of these device types.
    """

    def __init__(self, pddf_data=None):
        self._sensors = {name: [] for name in _SENSOR_CLASSES}
        data = getattr(pddf_data, 'data', {}) or {}

        for key in sorted(data):
            obj = data[key]
            if not isinstance(obj, dict):
                continue
            dev_type = obj.get('dev_info', {}).get('device_type')
            cls = _SENSOR_CLASSES.get(dev_type)
            if cls is not None:
                self._sensors[dev_type].append(cls(key, obj))

        LiquidCoolingBase.__init__(
            self,
            leakage_sensors_num=len(self._sensors['LEAK_SENSOR']),
            leakage_sensors_list=self._sensors['LEAK_SENSOR'])

    def get_name(self):
        return "Liquid Cooling"

    def get_presence(self):
        return any(self._sensors.values())

    def get_all_pressure_sensors(self):
        return self._sensors['PRESSURE_SENSOR']

    def get_all_flow_sensors(self):
        return self._sensors['FLOW_SENSOR']

    def get_all_humidity_sensors(self):
        return self._sensors['HUMIDITY_SENSOR']
