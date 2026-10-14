#!/usr/bin/env python3
#
# fan_drawer.py — PDDF FanDrawer wrapper
#
# Copyright (c) 2024, Juniper Networks, Inc.
# All rights reserved.
#

try:
    from sonic_platform_pddf_base.pddf_fan_drawer import PddfFanDrawer
except ImportError as e:
    raise ImportError("%s - required module not found" % e)


class FanDrawer(PddfFanDrawer):
    """Juniper PDDF Fan Drawer.

    A fan tray carries multiple fans but a single bi-color status LED, so the
    status LED is a property of the *drawer* (tray), not of an individual fan.
    The colour->value map and sysfs path live in the standard PDDF
    FANTRAY{N}_LED object in pddf-device.json (attr_devtype sysfs_led).
    """

    def __init__(self, tray_idx, pddf_data=None, pddf_plugin_data=None):
        PddfFanDrawer.__init__(self, tray_idx, pddf_data, pddf_plugin_data)
        from sonic_platform.override import load_impl
        self._impl = load_impl("FanDrawer", self)
        # A tray has several fans but one status LED. thermalctld's
        # _set_fan_led() drives the drawer LED once per fan with that fan's own
        # colour, so without aggregation the last fan processed wins and a tray
        # with a single failed fan can wrongly stay green. When
        # 'fantray_led_aggregate' is set in pddf-device.json, coerce the tray
        # LED to red unless *every* fan is healthy (order-independent). Opt-in,
        # so platforms that don't set it keep their exact previous behaviour.
        try:
            self._led_aggregate = bool(
                self.platform.get('fantray_led_aggregate', False))
        except (AttributeError, TypeError):
            self._led_aggregate = False

    def get_model(self):
        return self._impl.get_model()

    def get_serial(self):
        return self._impl.get_serial()

    def set_status_led(self, color):
        return self._impl.set_status_led(color)
