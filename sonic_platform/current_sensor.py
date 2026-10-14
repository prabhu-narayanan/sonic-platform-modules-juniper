#!/usr/bin/env python3
#
# current_sensor.py — Juniper CurrentSensor facade
#
# Thin facade over CurrentSensorImplBase. The impl selects a per-sensor
# backend from pddf-device.json:
#   - method=hwmon -> HwmonCurrentSensor (QFX5220 pmbus curr{N}_input)
#   - otherwise    -> PDDF-based sensor (PddfCurrentSensor)
#
# Copyright (c) 2026, Juniper Networks, Inc.
# All rights reserved.
#
# SPDX-License-Identifier: GPL-3.0-or-later

try:
    from sonic_platform_base.sensor_base import CurrentSensorBase
except ImportError as e:
    raise ImportError("%s - required module not found" % e)


class CurrentSensor(CurrentSensorBase):
    """Current sensor facade — owns the per-sensor backend (selected in
    __init__ from pddf-device.json); delegates the inherited public API to
    self._impl (CurrentSensorImplBase)."""

    def __init__(self, index, pddf_data=None, pddf_plugin_data=None):
        CurrentSensorBase.__init__(self)
        from sonic_platform.override import load_impl
        self._impl = load_impl("CurrentSensor", self)
        from sonic_platform.impl_base.current_sensor import (
              _is_hwmon_current_sensor, HwmonCurrentSensor,
              _JnprPddfCurrentSensor)
        if _is_hwmon_current_sensor(index, pddf_data):
              self._backend = HwmonCurrentSensor(
                 index, pddf_data, pddf_plugin_data)
        else:
              self._backend = _JnprPddfCurrentSensor(
                 index, pddf_data, pddf_plugin_data)

    def get_name(self):
        return self._impl.get_name()

    def get_presence(self):
        return self._impl.get_presence()

    def get_model(self):
        return self._impl.get_model()

    def get_serial(self):
        return self._impl.get_serial()

    def get_revision(self):
        return self._impl.get_revision()

    def get_status(self):
        return self._impl.get_status()

    def get_position_in_parent(self):
        return self._impl.get_position_in_parent()

    def is_replaceable(self):
        return self._impl.is_replaceable()

    def get_value(self):
        return self._impl.get_value()

    def get_high_threshold(self):
        return self._impl.get_high_threshold()

    def get_low_threshold(self):
        return self._impl.get_low_threshold()

    def set_high_threshold(self, value):
        return self._impl.set_high_threshold(value)

    def set_low_threshold(self, value):
        return self._impl.set_low_threshold(value)

    def get_high_critical_threshold(self):
        return self._impl.get_high_critical_threshold()

    def get_low_critical_threshold(self):
        return self._impl.get_low_critical_threshold()

    def set_high_critical_threshold(self, value):
        return self._impl.set_high_critical_threshold(value)

    def set_low_critical_threshold(self, value):
        return self._impl.set_low_critical_threshold(value)

    def get_minimum_recorded(self):
        return self._impl.get_minimum_recorded()

    def get_maximum_recorded(self):
        return self._impl.get_maximum_recorded()

