#!/usr/bin/env python3
#
# impl_base/asic_thermal.py — default AsicThermal platform implementation.
#
# Copyright (c) 2026, Juniper Networks, Inc.
# All rights reserved.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# AsicThermalImplBase holds the inherited ASIC-thermal public API only. State
# (index, thresholds, STATE_DB connection) and the STATE_DB mechanics live on
# the AsicThermal facade (self._host). Platforms override only what differs.

from sonic_platform.impl_base.temp_record import TemperatureRecordMixin


class AsicThermalImplBase(TemperatureRecordMixin):
    """Default ASIC die-temperature public API (state + mechanics on self._host)."""

    def __init__(self, host):
        self._host = host

    def get_name(self):
        return self._host.NAME

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

    def get_temperature(self):
        temperature = self._host._read_sdk_temp()
        if temperature is None:
            return None
        return self._record_temperature(round(temperature, 1))

    def get_high_threshold(self):
        return self._host._thr('high_threshold')

    def get_low_threshold(self):
        return None

    def get_high_critical_threshold(self):
        return self._host._thr('ot')

    def get_low_critical_threshold(self):
        return None

    def get_WTC(self):
        return self._host._thr('wtc')

    def get_WT(self):
        return self._host._thr('wt')

    def get_YAT(self):
        return self._host._thr('yat')

    def get_YATBF(self):
        return self._host._thr('yat_bad_fan')

    def get_RAT(self):
        return self._host._thr('rat')

    def get_RATBF(self):
        return self._host._thr('rat_bad_fan')

    def get_FT(self):
        return self._host._thr('fire_threshold')

    def get_high_threshold_bad_fan(self):
        return self._host._thr('high_threshold_bad_fan')
