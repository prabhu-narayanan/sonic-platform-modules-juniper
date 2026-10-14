#!/usr/bin/env python3
#
# impl_base/temp_record.py — min/max temperature recording for thermal impls.
#
# Copyright (c) 2026, Juniper Networks, Inc.
# All rights reserved.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# ThermalBase.get_minimum_recorded()/get_maximum_recorded() raise
# NotImplementedError by default. This mixin gives the thermal impls
# (Thermal, AsicThermal, SfpThermal) the common high/low-water tracking:
# each temperature read is funnelled through _record_temperature().


class TemperatureRecordMixin:
    """Tracks the lowest/highest temperature observed by this sensor."""

    # Class-level defaults; first write creates the per-instance value.
    _min_recorded = None
    _max_recorded = None

    def _record_temperature(self, temperature):
        """Update the high/low-water marks and return `temperature` unchanged."""
        if temperature is None:
            return None
        if self._min_recorded is None or temperature < self._min_recorded:
            self._min_recorded = temperature
        if self._max_recorded is None or temperature > self._max_recorded:
            self._max_recorded = temperature
        return temperature

    def get_minimum_recorded(self):
        if self._min_recorded is None:
            self._record_temperature(self.get_temperature())
        return self._min_recorded

    def get_maximum_recorded(self):
        if self._max_recorded is None:
            self._record_temperature(self.get_temperature())
        return self._max_recorded
