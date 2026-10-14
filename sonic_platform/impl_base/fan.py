#!/usr/bin/env python3
#
# impl_base/fan.py — default Fan platform implementation.
#
# Copyright (c) 2026, Juniper Networks, Inc.
# All rights reserved.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# FanImplBase holds the inherited Fan public API only. State, config parsing,
# and the hwmon/GPIO mechanics live on the Fan facade (self._host); FanBase
# constants and public re-entry go through self._host. Platforms override only
# the methods that differ.

import os

try:
    from sonic_platform.gpio_helper import read_gpio
    from sonic_platform.sysfs_util import sysfs_read_int, sysfs_write, find_hwmon_by_name
except ImportError as e:
    raise ImportError(str(e) + " - required module not found")


class FanImplBase:
    """Default per-platform Fan implementation (inherited public API only).

    State, config parsing, and the hwmon/GPIO mechanics live on the Fan facade
    (self._host); FanBase constants and public re-entry go through self._host.
    Platforms override only the methods that differ.
    """

    def __init__(self, host):
        self._host = host

    # ---- Identity ---- #
    def get_name(self):
        host = self._host
        if host._is_psu_fan:
            # _psu_index is already 1-based (from PddfPsu.psu_index)
            return "PSU{}_Fan{}".format(host._psu_index, host._fan_index + 1)

        plugin_data = getattr(host, 'plugin_data',
                              getattr(host, '_plugin_data', None))
        if plugin_data and 'FAN' in plugin_data:
            fan_plugin = plugin_data['FAN']
            if 'name' in fan_plugin:
                tray_key = str(host._fan_tray_index + 1)
                if tray_key in fan_plugin['name']:
                    return fan_plugin['name'][tray_key]

        return "FanTray{}_Fan{}".format(
            host._fan_tray_index + 1, host._fan_index + 1)

    def get_model(self):
        return self._host._fan_cfg.get('model', 'N/A')

    def get_serial(self):
        return "N/A"

    def get_presence(self):
        host = self._host
        if host._is_psu_fan:
            return True
        if host._gpio_pin is not None:
            value = read_gpio(host._gpio_pin)
            if value is not None and value == host._gpio_active_value:
                return True
            if value is not None:
                return False
        speed = host._read_hwmon_fan_rpm()
        return speed is not None and speed > 0

    def get_status(self):
        host = self._host
        if not host.get_presence():
            return False
        rpm = host._read_hwmon_fan_rpm()
        if rpm is None or rpm <= 0:
            return False
        min_rpm, _ = host._get_rpm_alarm_range()
        return rpm >= min_rpm

    def get_direction(self):
        host = self._host
        direction = host._fan_cfg.get('direction', 'exhaust')
        if direction == 'intake':
            return host.FAN_DIRECTION_INTAKE
        return host.FAN_DIRECTION_EXHAUST

    def get_speed(self):
        host = self._host
        rpm = host._read_hwmon_fan_rpm()
        if rpm is not None and rpm < host._min_rpm:
            return 0
        pwm = host._read_hwmon_pwm_255()
        if pwm is None or host._pwm_max <= 0:
            return 0
        speed_pct = int(round((pwm * 100) / float(host._pwm_max)))
        return min(max(speed_pct, 0), 100)

    def get_speed_rpm(self):
        rpm = self._host._read_hwmon_fan_rpm()
        return rpm if rpm is not None else 0

    def get_target_speed(self):
        host = self._host
        pwm = host._read_hwmon_pwm_255()
        if pwm is None or host._pwm_max <= 0:
            return 0
        target_pct = int(round((pwm * 100) / float(host._pwm_max)))
        return min(max(target_pct, 0), 100)

    def get_speed_tolerance(self):
        return int(self._host._fan_cfg.get('speed_tolerance', '10'))

    def get_min_rpm(self):
        min_rpm, _ = self._host._get_rpm_alarm_range()
        return min_rpm

    def get_max_rpm(self):
        _, max_rpm = self._host._get_rpm_alarm_range()
        return max_rpm

    def set_speed(self, speed):
        host = self._host
        if not isinstance(speed, int) or speed < 0 or speed > 100:
            return False
        pwm_val = int(round(speed * host._pwm_max / 100.0))
        if host._pwm_path is not None:
            if sysfs_write(host._pwm_path, pwm_val):
                return True
            host._pwm_path = None
        path = host._resolve_pwm_path()
        if path is None:
            return False
        if sysfs_write(path, pwm_val):
            host._pwm_path = path
            return True
        return False

    def set_status_led(self, color):
        host = self._host
        if host._led_ok_path is None or host._led_fail_path is None:
            return False
        if color == host.STATUS_LED_COLOR_GREEN:
            return (sysfs_write(host._led_ok_path, 1)
                    and sysfs_write(host._led_fail_path, 0))
        elif color == host.STATUS_LED_COLOR_RED:
            return (sysfs_write(host._led_ok_path, 0)
                    and sysfs_write(host._led_fail_path, 1))
        elif color == host.STATUS_LED_COLOR_OFF:
            return (sysfs_write(host._led_ok_path, 0)
                    and sysfs_write(host._led_fail_path, 0))
        return False

    def get_status_led(self):
        host = self._host
        if not host.get_presence():
            return host.STATUS_LED_COLOR_OFF
        fan_ok = host.get_status()
        if host._led_ok_path and host._led_fail_path:
            ok_val = sysfs_read_int(host._led_ok_path)
            fail_val = sysfs_read_int(host._led_fail_path)
            if ok_val is not None and fail_val is not None:
                if ok_val > 0 and fail_val == 0:
                    return host.STATUS_LED_COLOR_GREEN
                elif fail_val > 0 and ok_val == 0:
                    return host.STATUS_LED_COLOR_RED
        if fan_ok:
            return host.STATUS_LED_COLOR_GREEN
        return host.STATUS_LED_COLOR_RED

    def is_replaceable(self):
        return True

    def get_position_in_parent(self):
        return self._host._fan_index + 1
