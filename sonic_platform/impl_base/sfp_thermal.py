#!/usr/bin/env python3
#
# impl_base/sfp_thermal.py — default SfpThermal platform implementation.
#
# Copyright (c) 2026, Juniper Networks, Inc.
# All rights reserved.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# SfpThermalImplBase holds the inherited per-port optic-thermal public API. The
# facade (sonic_platform/sfp_thermal.py, a ThermalBase) owns state (port index,
# sfp, thresholds) and the _thr mechanic; this class reads them via self._host.

from sonic_platform.impl_base.temp_record import TemperatureRecordMixin


class SfpThermalImplBase(TemperatureRecordMixin):
    """Default thermal implementation backed by SFP/OSFP DOM temperature."""

    def __init__(self, host):
        self._host = host

    def get_name(self):
        return "et-0/0/{}".format(self._host._port_index)

    def get_presence(self):
        return self._host._sfp.get_presence()

    def get_status(self):
        return self._host._sfp.get_presence()

    def get_model(self):
        return "N/A"

    def get_serial(self):
        return "N/A"

    def is_replaceable(self):
        return False

    def get_position_in_parent(self):
        return self._host._port_index + 1

    def get_temperature(self):
        """Read temperature from transceiver DOM."""
        host = self._host
        if not host._sfp.get_presence():
            return 0.0
        try:
            temp = host._sfp.get_temperature()
            if temp is not None:
                return self._record_temperature(float(temp))
        except Exception:
            pass
        return 0.0

    def get_high_threshold(self):
        return self._host._thr('temphighwarning', self._host._thr('high_threshold'))

    def get_low_threshold(self):
        return self._host._thr('templowwarning')

    def get_high_critical_threshold(self):
        return self._host._thr('temphighalarm', self._host._thr('ot'))

    def get_low_critical_threshold(self):
        return self._host._thr('templowalarm')

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
