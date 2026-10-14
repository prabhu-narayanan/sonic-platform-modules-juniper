#!/usr/bin/env python3
#
# Name: watchdog.py, version: 3.0
#
# Description: Hardware watchdog wrapper for Juniper PDDF platforms.
#
# PddfWatchdog provides the Linux watchdog implementation used by Juniper
# PDDF platforms. Keep this file platform-neutral; add overrides here only
# when a platform needs behavior beyond the shared PDDF interface.
#
# Copyright (c) 2026, Juniper Networks, Inc.
# Copyright (c) 2026, Hewlett Packard Enterprise Development LP
# All rights reserved.
#

try:
    from sonic_platform_pddf_base.pddf_watchdog import PddfWatchdog
except ImportError as e:
    raise ImportError(str(e) + "- required module not found")


DEFAULT_TIMEOUT = 180
WDT_COMMON_ERROR = -1
SUPPORTED_WATCHDOG_IDENTITIES = ("iTCO_wdt", "wdat_wdt", "HPE FPGA Watchdog")


class Watchdog(PddfWatchdog):
    """PDDF watchdog class for Juniper platforms."""

    def __init__(self):
        from sonic_platform.override import load_impl
        self._impl = load_impl("Watchdog", self)
        if not all(hasattr(self, attr) for attr in ("_get_wdt", "_read_file", "_gettimeout")):
            PddfWatchdog.__init__(self)
            return

        self.wdt_main_dev_name = self._get_wdt_main_dev_name()
        if self.wdt_main_dev_name is None:
            # No watchdog with a supported identity found — fall back to the base
            # PDDF watchdog which discovers the device without an identity filter.
            PddfWatchdog.__init__(self)
            return

        self.status_path = "/sys/class/watchdog/%s/status" % self.wdt_main_dev_name
        self.state_path = "/sys/class/watchdog/%s/state" % self.wdt_main_dev_name
        self.timeout_path = "/sys/class/watchdog/%s/timeout" % self.wdt_main_dev_name

        was_armed = self._read_armed_state()
        self.watchdog, self.wdt_main_dev_name = self._get_wdt()
        if self.watchdog is None:
            PddfWatchdog.__init__(self)
            return

        if was_armed is False and self._read_armed_state() is True:
            self._disable()

        self.armed = bool(was_armed)
        self.timeout = self._read_timeout()

    def _is_wd_main(self, dev):
        identity = self._read_file("/sys/class/watchdog/{}/identity".format(dev))
        return identity in SUPPORTED_WATCHDOG_IDENTITIES

    def _get_wdt_main_dev_name(self):
        try:
            return next(dev for dev in sorted(__import__("os").listdir("/dev/"))
                        if dev.startswith("watchdog") and self._is_wd_main(dev))
        except StopIteration:
            return None

    def _read_timeout(self):
        try:
            return self._gettimeout(self.timeout_path)
        except Exception:
            timeout = self._read_file(self.timeout_path)
            try:
                return int(timeout)
            except (TypeError, ValueError):
                return DEFAULT_TIMEOUT

    def _read_armed_state(self):
        state = self._read_file(self.state_path)
        if state == WDT_COMMON_ERROR:
            return None

        state = state.lower()
        if state in ("active", "running"):
            return True
        if state in ("inactive", "stopped"):
            return False
        return None

    def is_armed(self):
        return self._impl.is_armed()

    def disarm(self):
        return self._impl.disarm()

    def get_remaining_time(self):
        return self._impl.get_remaining_time()


# Backward-compatibility for older Juniper chassis code/tests that still
# import WatchdogImplBase from sonic_platform.watchdog.
WatchdogImplBase = Watchdog
