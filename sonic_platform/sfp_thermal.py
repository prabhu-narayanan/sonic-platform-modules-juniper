#!/usr/bin/env python3
#
# sfp_thermal.py — Per-port optic thermal sensor for EM policy
#
# Creates a ThermalBase object for each SFP/OSFP port that reads
# temperature from the transceiver DOM and uses OPTIC_THRESHOLDS
# from pddf-device.json for alarm classification.
#
# These appear as "et-0/0/{port}" in 'show platform temperature'.
#
# Copyright (c) 2025, Juniper Networks, Inc.
# All rights reserved.
#

import json

try:
    from sonic_platform_base.thermal_base import ThermalBase
except ImportError as e:
    raise ImportError("%s - required module not found" % e)


class SfpThermal(ThermalBase):
    """Thermal sensor backed by SFP/OSFP DOM temperature.

    Each instance wraps one SFP object and exposes its DOM temperature
    as a standard ThermalBase sensor.  Thresholds come from
    OPTIC_THRESHOLDS in pddf-device.json.
    """

    def __init__(self, port_index, sfp, optic_thresholds):
        ThermalBase.__init__(self)
        self.is_sfp_thermal = True
        from sonic_platform.override import load_impl
        self._impl = load_impl("SfpThermal", self)
        self._port_index = port_index
        self._sfp = sfp
        self._thresholds = optic_thresholds or {}

    def _thr(self, key, default=None):
        try:
            val = self._thresholds.get(key)
            return float(val) if val is not None else default
        except (TypeError, ValueError):
            return default

    def get_name(self):
        return self._impl.get_name()

    def get_presence(self):
        return self._impl.get_presence()

    def get_status(self):
        return self._impl.get_status()

    def get_model(self):
        return self._impl.get_model()

    def get_serial(self):
        return self._impl.get_serial()

    def is_replaceable(self):
        return self._impl.is_replaceable()

    def get_position_in_parent(self):
        return self._impl.get_position_in_parent()

    def get_temperature(self):
        return self._impl.get_temperature()

    def get_minimum_recorded(self):
        return self._impl.get_minimum_recorded()

    def get_maximum_recorded(self):
        return self._impl.get_maximum_recorded()

    def get_high_threshold(self):
        return self._impl.get_high_threshold()

    def get_low_threshold(self):
        return self._impl.get_low_threshold()

    def get_high_critical_threshold(self):
        return self._impl.get_high_critical_threshold()

    def get_low_critical_threshold(self):
        return self._impl.get_low_critical_threshold()

    def get_WTC(self):
        return self._impl.get_WTC()

    def get_WT(self):
        return self._impl.get_WT()

    def get_YAT(self):
        return self._impl.get_YAT()

    def get_YATBF(self):
        return self._impl.get_YATBF()

    def get_RAT(self):
        return self._impl.get_RAT()

    def get_RATBF(self):
        return self._impl.get_RATBF()

    def get_FT(self):
        return self._impl.get_FT()

    def get_high_threshold_bad_fan(self):
        return self._impl.get_high_threshold_bad_fan()
