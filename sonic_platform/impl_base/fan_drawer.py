#!/usr/bin/env python3
#
# impl_base/fan_drawer.py — default FanDrawer platform implementation.
#
# Copyright (c) 2026, Juniper Networks, Inc.
# All rights reserved.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# FanDrawerImplBase owns the tray-LED aggregation behavior. The owning
# FanDrawer facade (a PddfFanDrawer) is self._host; base-class state
# (platform, fantray_index, _fan_list, pddf_obj) is read through it.


class FanDrawerImplBase:
    """Default per-platform FanDrawer implementation."""

    def __init__(self, host):
        self._host = host

    def get_model(self):
        """Return model from first fan's EEPROM."""
        fan_drawer = self._host
        if fan_drawer._fan_list:
            return fan_drawer._fan_list[0].get_model()
        return 'N/A'

    def get_serial(self):
        """Return serial from first fan's EEPROM."""
        fan_drawer = self._host
        if fan_drawer._fan_list:
            return fan_drawer._fan_list[0].get_serial()
        return 'N/A'

    def set_status_led(self, color):
        """Set the fan-tray status LED via standard PDDF set_system_led_color.

        The colour->value map and the sysfs path live in the FANTRAY{N}_LED
        object in pddf-device.json, not in code. get_status_led is inherited
        from PddfFanDrawer, which reads the same object back.
        """
        fan_drawer = self._host
        led_name = "FANTRAY{}_LED".format(fan_drawer.fantray_index)
        # Aggregate the whole tray's health into the single LED: a request to
        # show green is honoured only when every fan in the tray is healthy.
        if (self._host._led_aggregate
                and color == fan_drawer.STATUS_LED_COLOR_GREEN
                and not fan_drawer.get_status()):
            color = fan_drawer.STATUS_LED_COLOR_RED
        result, _msg = fan_drawer.pddf_obj.set_system_led_color(led_name, color)
        return result
