#!/usr/bin/env python3
#
# impl_base/thermal.py — default Thermal platform implementation.
#
# Copyright (c) 2026, Juniper Networks, Inc.
# All rights reserved.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# ThermalImplBase holds the inherited Thermal public API (name, temperature,
# thresholds, custom EM-policy thresholds). The facade (sonic_platform/
# thermal.py, a PddfThermal) owns state and the read mechanics (_get_dev_attr,
# IIO/PSU-pmbus helpers); this class reads them via self._host.

from sonic_platform.impl_base.temp_record import TemperatureRecordMixin

try:
    from sonic_platform_pddf_base.pddf_thermal import PddfThermal
except ImportError as e:
    raise ImportError("%s - required module not found" % e)


class ThermalImplBase(TemperatureRecordMixin):
    """Default per-platform Thermal implementation.

    self._host is the owning Thermal (a PddfThermal). Standard SONiC thresholds
    are read from TEMP{N}.i2c.dev_attr; custom EM-policy thresholds (wtc/wt/yat/
    rat/fire_threshold/...) feed thermal_infos.py. Framework fallbacks call
    PddfThermal.X(self._host).
    """

    def __init__(self, host):
        self._host = host

    # ---- Name (JSON dev_attr under i2c.dev_attr) ---- #
    def get_name(self):
        host = self._host
        if host.is_psu_thermal:
            return "PSU{}_TEMP{}".format(host.thermals_psu_index, host.thermal_index)
        try:
            return str(host.thermal_obj['i2c']['dev_attr']['display_name'])
        except (KeyError, TypeError):
            return host.thermal_obj_name

    def get_presence(self):
        return PddfThermal.get_presence(self._host)

    def get_status(self):
        return PddfThermal.get_presence(self._host)

    def get_model(self):
        return "N/A"

    def get_serial(self):
        return "N/A"

    def is_replaceable(self):
        return False

    def get_position_in_parent(self):
        return PddfThermal.get_position_in_parent(self._host)

    def get_temperature(self):
        host = self._host
        if host.is_psu_thermal:
            temp = host._get_psu_hwmon_temperature()
            if temp is not None:
                return self._record_temperature(temp)
        if host._is_iio_device():
            temp = host._get_iio_temperature()
            if temp is not None:
                return self._record_temperature(temp)
        return self._record_temperature(PddfThermal.get_temperature(host))

    # ---- Standard SONiC threshold overrides (read from dev_attr) ---- #
    def get_high_threshold(self):
        host = self._host
        if host.is_psu_thermal:
            temp = host._read_psu_pmbus_temp('max')
            if temp is not None and temp > 0:
                return temp
            temp = host._get_psu_pddf_high_threshold()
            if temp is not None and temp > 0:
                return temp
        return host._get_dev_attr('high_threshold')

    def get_high_critical_threshold(self):
        host = self._host
        if host.is_psu_thermal:
            temp = host._read_psu_pmbus_temp('crit')
            if temp is not None and temp > 0:
                return temp
            return host._get_dev_attr('rat')
        val = host._get_dev_attr('rat')
        if val is not None:
            return val
        return PddfThermal.get_high_critical_threshold(host)

    def get_low_threshold(self):
        host = self._host
        if host.is_psu_thermal:
            return None
        return PddfThermal.get_low_threshold(host)

    def get_low_critical_threshold(self):
        host = self._host
        if host.is_psu_thermal:
            return None
        return PddfThermal.get_low_critical_threshold(host)

    # ---- Custom policy thresholds (called by thermal_infos.py) ---- #
    def get_WTC(self):
        """Warm temperature control — base temp for fan speed curve."""
        return self._host._get_dev_attr('wtc')

    def get_WT(self):
        """Warm threshold — fan speed ramp start."""
        return self._host._get_dev_attr('wt')

    def get_YAT(self):
        """Yellow alarm threshold — minor alarm."""
        return self._host._get_dev_attr('yat')

    def get_YATBF(self):
        """Yellow alarm threshold with bad fan."""
        return self._host._get_dev_attr('yat_bad_fan')

    def get_RAT(self):
        """Red alarm threshold — major alarm / shutdown trigger."""
        return self._host._get_dev_attr('rat')

    def get_RATBF(self):
        """Red alarm threshold with bad fan."""
        return self._host._get_dev_attr('rat_bad_fan')

    def get_FT(self):
        """Fire threshold — immediate shutdown."""
        return self._host._get_dev_attr('fire_threshold')

    def get_high_threshold_bad_fan(self):
        """High threshold with degraded fan."""
        return self._host._get_dev_attr('high_threshold_bad_fan')
