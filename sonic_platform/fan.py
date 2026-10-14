#!/usr/bin/env python3
#
# fan.py — Generic PDDF-compatible Fan class for SONiC Platform API
#
# Copyright (c) 2026, Hewlett Packard Enterprise Development LP
# All rights reserved.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Hardware-agnostic fan implementation. ALL platform-specific values come
# from pddf-device.json FAN_CTRL.i2c.dev_attr:
#
#   hwmon_name       — kernel hwmon device name (e.g., "i2cs_fan")
#   max_front_rpm    — max RPM for rotor1 / outlet fan (fan_index 0)
#   max_rear_rpm     — max RPM for rotor2 / inlet fan  (fan_index 1)
#   speed_tolerance  — acceptable speed variance (%)
#   pwm_max          — PWM ceiling (e.g., "255")
#   fan_start_idx    — which fan_index within a tray is the outlet fan
#                      (fan_num % FAN_TABLE_CNT == fan_start_idx → outlet)
#   direction        — airflow direction ("exhaust" or "intake")
#   model            — fan module part number
#   gpio_label       — gpiochip label for tray presence
#   gpio_trayN_offset — GPIO offset for tray N presence (active-high)
#   led_ok_pattern   — LED sysfs name pattern for OK LED ("fan{}-ok")
#   led_fail_pattern — LED sysfs name pattern for fail LED ("fan{}-fail")
#
# To support a new platform, change ONLY the JSON — zero Python changes.

import os
import syslog

try:
    from sonic_platform_base.fan_base import FanBase
    from sonic_platform.gpio_helper import resolve_gpio_pin
    from sonic_platform.sysfs_util import sysfs_read_int, find_hwmon_by_name
except ImportError as e:
    raise ImportError(str(e) + " - required module not found")

SYSLOG_IDENTIFIER = "fan"

# LED brightness values
LED_OFF = 0
LED_GREEN = 1
LED_RED = 2


def _log_err(msg):
    syslog.openlog(SYSLOG_IDENTIFIER)
    syslog.syslog(syslog.LOG_ERR, msg)
    syslog.closelog()


class Fan(FanBase):
    """
    Generic Fan class — reads ALL configuration from pddf-device.json.

    Constructor signature is compatible with PddfFanDrawer, which calls:
        Fan(tray_idx, fan_idx, pddf_data, pddf_plugin_data)

    Fan indexing:
      - tray_idx:  0-based fan tray index
      - fan_idx:   0-based fan index within tray (0=front/outer, 1=rear/inner)
      - hwmon idx: (tray_idx * fans_per_tray + fan_idx) + 1  (1-based)
    """

    def __init__(self, fan_tray_index, fan_index=0, pddf_data=None,
                 pddf_plugin_data=None, is_psu_fan=False, psu_index=0):
        FanBase.__init__(self)
        from sonic_platform.override import load_impl
        self._impl = load_impl("Fan", self)
        self.pddf_obj = pddf_data
        self.plugin_data = pddf_plugin_data
        self._fan_tray_index = fan_tray_index
        self._fan_index = fan_index
        self._is_psu_fan = is_psu_fan
        self._psu_index = psu_index

        # Read platform counts from JSON
        if pddf_data:
            platform = pddf_data.get_platform()
            self._num_fantrays = platform.get('num_fantrays', 3)
            self._fans_per_tray = platform.get('num_fans_pertray', 2)
        else:
            self._num_fantrays = 3
            self._fans_per_tray = 2

        # Read FAN_CTRL dev_attr from JSON (all platform-specific config)
        self._fan_cfg = {}
        if pddf_data and 'FAN_CTRL' in pddf_data.data:
            self._fan_cfg = pddf_data.data['FAN_CTRL'].get('i2c', {}).get('dev_attr', {})

        # fan_start_idx: determines which fan_index within a tray
        # is the outlet (rear) fan.  From Fan_qfx5k_shared.cpp:
        #   if (fan_num % FAN_TABLE_CNT == fan_start_idx) -> outlet fan
        # Default is "0" — first fan in each tray is the outlet fan.
        self._fan_start_idx = int(self._fan_cfg.get('fan_start_idx', '0'))

        # Hwmon fan index (1-based) for fanN_input / pwmN
        total_fans = self._num_fantrays * self._fans_per_tray
        self._hwmon_fan_index = (fan_tray_index * self._fans_per_tray) + fan_index
        if self._hwmon_fan_index >= total_fans:
            self._hwmon_fan_index = total_fans - 1

        #   rotor1 (fan_index 0) = outlet fan -> max_front_rpm
        #   rotor2 (fan_index 1) = inlet fan  -> max_rear_rpm
        # "front/rear" in JSON = physical rotor position in tray
        #
        # Platform-specific values MUST be set in pddf-device.json:
        #   QFX5250: 21800 / 20500
        #   QFX5140: 29000 / 29000
        #   PTX10002: 23000 / 23000
        # Default 29000 is a safe ceiling (highest across platforms) —
        # ensures no false overspeed alarms if JSON is missing/malformed.
        if self._is_outlet_fan():
            self._max_rpm = int(self._fan_cfg.get('max_front_rpm', '29000'))
        else:
            self._max_rpm = int(self._fan_cfg.get('max_rear_rpm', '29000'))

        # min_rpm from FDT: below this RPM the fan is considered failed/stuck
        # (qfx5250_64oe_rotor1/2_attributes: min_rpm = <2500>)
        self._min_rpm = int(self._fan_cfg.get('min_rpm', '2500'))

        self._pwm_max = int(self._fan_cfg.get('pwm_max', '255'))

        # Cached sysfs paths (populated on first successful read,
        # invalidated on I/O error to trigger re-discovery)
        self._rpm_path = None
        self._pwm_path = None

        # Pre-compute LED brightness sysfs paths (stable for process life)
        ok_pattern = self._fan_cfg.get('led_ok_pattern', '')
        fail_pattern = self._fan_cfg.get('led_fail_pattern', '')
        if (ok_pattern and fail_pattern
                and fan_tray_index < self._num_fantrays):
            self._led_ok_path = "/sys/class/leds/{}/brightness".format(
                ok_pattern.format(fan_tray_index))
            self._led_fail_path = "/sys/class/leds/{}/brightness".format(
                fail_pattern.format(fan_tray_index))
        else:
            self._led_ok_path = None
            self._led_fail_path = None

        # Resolve GPIO pin for this fan tray's presence detection
        self._gpio_pin = None
        if not is_psu_fan:
            gpio_label = self._fan_cfg.get('gpio_label', '')
            offset_key = 'gpio_tray{}_offset'.format(fan_tray_index)
            offset_str = self._fan_cfg.get(offset_key)
            if gpio_label and offset_str is not None:
                self._gpio_pin = resolve_gpio_pin(gpio_label, offset_str)
                if self._gpio_pin is None:
                    _log_err("Fan: gpiochip label '{}' not found".format(gpio_label))
            # GPIO active value: "1" = active-high (default), "0" = active-low
            self._gpio_active_value = self._fan_cfg.get('gpio_active_value', '1')

    # =========================================================================
    # Internal: inlet/outlet fan identification
    # =========================================================================

    def _is_outlet_fan(self):
        """Determine if this fan is an outlet (rear) fan.

        In SONiC, self._fan_index is already the position within the tray
        (equivalent to fan_num % FAN_TABLE_CNT), so:
            fan_index == fan_start_idx  -> outlet (rear) fan
            fan_index != fan_start_idx  -> inlet (front) fan
        """
        return (self._fan_index % self._fans_per_tray) == self._fan_start_idx

    # =========================================================================
    # Internal: hwmon sysfs access
    # =========================================================================

    def _resolve_pwm_path(self):
        """Resolve pwmN sysfs path for this fan.

        Some fan controllers (e.g. Altera S32AFC) expose a single shared PWM
        (pwm1) that drives every rotor; without 'shared_pwm' the per-fan pwmN
        does not exist and every fan but the first reads speed 0.
        """
        hwmon_name = self._fan_cfg.get('hwmon_name', '')
        if not hwmon_name:
            return None
        hwmon_path = find_hwmon_by_name(hwmon_name)
        if hwmon_path is None:
            return None
        if str(self._fan_cfg.get('shared_pwm', '0')).lower() in ('1', 'true'):
            hwmon_idx = 1
        else:
            hwmon_idx = self._hwmon_fan_index + 1
        return os.path.join(hwmon_path, "pwm{}".format(hwmon_idx))

    def _read_hwmon_pwm_255(self):
        """Read current PWM value from hwmon pwmN (0..pwm_max)."""
        if self._pwm_path is not None:
            val = sysfs_read_int(self._pwm_path)
            if val is not None:
                return val
            self._pwm_path = None
        path = self._resolve_pwm_path()
        if path is None:
            return None
        val = sysfs_read_int(path)
        if val is not None:
            self._pwm_path = path
        return val

    def _get_rpm_alarm_range(self):
        """Return (min_rpm, max_rpm) for current PWM using JSON metadata.

        Fan identification:
          - outlet fan (fan_index == fan_start_idx) -> columns 1,2
            (outlet_speed_range in qfx5250_64oe_fan_fdt.h)
          - inlet fan  (fan_index != fan_start_idx) -> columns 3,4
            (inlet_speed_range in qfx5250_64oe_fan_fdt.h)

        JSON format: [pwm_pct, outlet_min, outlet_max, inlet_min, inlet_max]

        Driver PWM conversion:
        The jnx-fancpld driver converts CPLD register (0-100 scale) to
        hwmon sysfs (0-255 scale) using pwm_reg_max=100:
            sysfs_pwm = cpld_reg * 255 / 100
        So sysfs_pct = sysfs_pwm * 100 / 255 directly equals the CPLD
        duty cycle percentage. 

        Legacy: older driver versions used pwm_mask as divisor which
        inflated sysfs values. The driver_pwm_mask JSON key is retained
        for backward compat but defaults to 100.
        """
        ranges = self._fan_cfg.get('fan_speed_alarm_ranges')
        if not isinstance(ranges, list) or not ranges:
            return 0, self._max_rpm

        pwm_255 = self._read_hwmon_pwm_255()
        if pwm_255 is None:
            return 0, self._max_rpm

        try:
            # Format : [pwm_pct, outlet_min, outlet_max, inlet_min, inlet_max]
            if all(isinstance(row, list) and len(row) >= 5 for row in ranges):
                sysfs_pct = int(round((pwm_255 * 100) / float(self._pwm_max)))

                # With the current driver (pwm_reg_max=100), sysfs_pct
                # already represents the true CPLD duty cycle percentage.
                # driver_pwm_mask=100, cpld_max=100 → duty = sysfs_pct.
                # Override via JSON for legacy driver versions if needed.
                driver_mask = int(self._fan_cfg.get('driver_pwm_mask', '100'))
                cpld_max = int(self._fan_cfg.get('cpld_duty_max', '100'))
                duty = min(sysfs_pct * driver_mask // cpld_max, 100)

                best = min(ranges, key=lambda row: abs(int(row[0]) - duty))
                # From FDT: outlet_speed_range = columns 1,2
                #           inlet_speed_range  = columns 3,4
                if self._is_outlet_fan():
                    return int(best[1]), int(best[2])
                return int(best[3]), int(best[4])

        except Exception as e:
            _log_err("Fan: failed to parse fan_speed_alarm_ranges - {}".format(e))

        return 0, self._max_rpm

    def _read_hwmon_fan_rpm(self):
        """Read RPM from hwmon fanN_input (N is 1-based).

        Uses a cached sysfs path to avoid repeated hwmon lookup and
        string construction on every thermal daemon poll cycle (15s).
        """
        # Fast path: use cached location
        if self._rpm_path is not None:
            val = sysfs_read_int(self._rpm_path)
            if val is not None:
                return val
            # Path went stale (hwmon renumbered?) — re-discover
            self._rpm_path = None
        hwmon_name = self._fan_cfg.get('hwmon_name', '')
        if not hwmon_name:
            return None
        hwmon_path = find_hwmon_by_name(hwmon_name)
        if hwmon_path is None:
            return None
        hwmon_idx = self._hwmon_fan_index + 1
        path = os.path.join(hwmon_path, "fan{}_input".format(hwmon_idx))
        val = sysfs_read_int(path)
        if val is not None:
            self._rpm_path = path
        return val

    def get_name(self):
        return self._impl.get_name()

    def get_model(self):
        return self._impl.get_model()

    def get_serial(self):
        return self._impl.get_serial()

    def get_presence(self):
        return self._impl.get_presence()

    def get_status(self):
        return self._impl.get_status()

    def get_direction(self):
        return self._impl.get_direction()

    def get_speed(self):
        return self._impl.get_speed()

    def get_speed_rpm(self):
        return self._impl.get_speed_rpm()

    def get_target_speed(self):
        return self._impl.get_target_speed()

    def get_speed_tolerance(self):
        return self._impl.get_speed_tolerance()

    def get_min_rpm(self):
        return self._impl.get_min_rpm()

    def get_max_rpm(self):
        return self._impl.get_max_rpm()

    def set_speed(self, speed):
        return self._impl.set_speed(speed)

    def set_status_led(self, color):
        return self._impl.set_status_led(color)

    def get_status_led(self):
        return self._impl.get_status_led()

    def is_replaceable(self):
        return self._impl.is_replaceable()

    def get_position_in_parent(self):
        return self._impl.get_position_in_parent()
