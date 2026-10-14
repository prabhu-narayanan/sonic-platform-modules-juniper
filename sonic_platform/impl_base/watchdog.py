#!/usr/bin/env python3
#
# impl_base/watchdog.py — default Watchdog platform implementation.
#
# Copyright (c) 2026, Juniper Networks, Inc.
# Copyright (c) 2026, Hewlett Packard Enterprise Development LP
# All rights reserved.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# WatchdogImplBase holds the inherited watchdog public API (disarm/is_armed/
# get_remaining_time). The facade (sonic_platform/watchdog.py, a PddfWatchdog)
# owns discovery/config and the read helpers; this class reads state
# and calls those helpers via self._host.

DEFAULT_TIMEOUT = 180
WDT_COMMON_ERROR = -1
SUPPORTED_WATCHDOG_IDENTITIES = ("iTCO_wdt", "wdat_wdt", "HPE FPGA Watchdog")


class WatchdogImplBase:
    """Default PDDF watchdog implementation for Juniper platforms."""

    def __init__(self, host):
        self._host = host

    def is_armed(self):
        armed = self._host._read_armed_state()
        if armed is not None:
            self._host.armed = armed
        return self._host.armed

    def disarm(self):
        try:
            self._host._disable()
        except IOError:
            return False

        self._host.armed = False
        return not self.is_armed()

    def get_remaining_time(self):
        if not self.is_armed():
            return WDT_COMMON_ERROR

        try:
            return self._host._gettimeleft()
        except IOError:
            return WDT_COMMON_ERROR
