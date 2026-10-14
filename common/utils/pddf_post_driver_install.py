#!/usr/bin/env python3
#
# Common PDDF post-driver-install hook (all Juniper PDDF platforms)
#
# Copyright (C) 2026 Juniper Networks
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
#
# Invoked after pddf_util.py modprobes std_kos/pddf_kos/custom_kos and before
# device_install() creates clients described by pddf-device.json. Some
# platforms still create PCA954x mux clients through PDDF, with dynamic channel
# numbering; QFX5140/QFX5250 instead create their muxes through MFD platform
# cells and assign static channel buses in platform data.
#
# FPGA-backed I2C adapters and MFD-created mux clients may probe asynchronously
# or defer until their parent adapter exists. Waiting for the buses declared by
# the active JSON prevents device_install() from racing adapter registration.
# The wait also protects platforms whose PDDF-created mux channel buses remain
# dynamically allocated.
#
# A plain `udevadm settle` is NOT sufficient: it only waits on uevents that
# are already queued. If the i2c master's underlying PCI device hasn't even
# been enumerated yet (observed in practice: PCIe hotplug bridge link
# training can still be in progress well after modprobe() returns), there is
# nothing queued for it and settle returns immediately with a false all-clear
# -- device_install() then races ahead and hits the crash above. The same
# race also affects standard (non-custom) adapters: e.g. the CPU's own i801
# SMBus controller can still be probing when pddf-device.json's hardcoded
# "parent_bus": "0x1" assumption is acted on, producing benign but noisy
# "Directory nonexistent" / "command failed" errors for its child devices.
#
# To close this race, the hook reads every literal (non-symbolic) parent_bus value
# out of the currently active platform's own pddf-device.json and waits for
# each corresponding /sys/bus/i2c/devices/i2c-<N> to exist, bounded by an
# overall timeout. This is still generic (no hardcoded platform data in this
# file) -- it just reads whatever topology each platform's own JSON declares.
# As a fallback for dynamically-numbered pca9548 mux channels that have no
# fixed bus number in the JSON at all, it also re-settles in a loop and waits
# for the total number of registered i2c adapters to stop growing across
# consecutive samples.

import glob
import json
import os
import subprocess
import time

from sonic_py_common import device_info
from sonic_py_common.logger import Logger

SYSLOG_IDENTIFIER = "juniper-utils"

SETTLE_TIMEOUT_SEC = 30
STATIC_BUS_WAIT_SEC = 20
STATIC_BUS_POLL_INTERVAL_SEC = 0.5
STABLE_CHECK_INTERVAL_SEC = 0.5
STABLE_CHECKS_REQUIRED = 2
MAX_STABLE_WAIT_SEC = 10


def log_info(msg):
    logger = Logger(SYSLOG_IDENTIFIER)
    logger.set_min_log_priority_info()
    logger.log_info(msg)


def log_error(msg):
    logger = Logger(SYSLOG_IDENTIFIER)
    logger.set_min_log_priority_error()
    logger.log_error(msg)


def udev_settle():
    result = subprocess.run(["udevadm", "settle", f"--timeout={SETTLE_TIMEOUT_SEC}"],
                             capture_output=True, text=True)
    if result.returncode != 0:
        log_error(f"udevadm settle failed: {result.stderr.strip()}")


def count_i2c_adapters():
    return len(glob.glob("/sys/bus/i2c/devices/i2c-*"))


def get_static_parent_buses():
    """Return the set of literal (non-symbolic) parent_bus numbers declared
    anywhere in the active platform's pddf-device.json. A parent_bus value
    like "0x8" is a real, fixed bus number; a value like "TMC_ROOT" is a
    symbolic reference to another device and is not a bus number itself, so
    those are skipped (int(..., 0) raises and we move on)."""
    try:
        json_path = f"{device_info.get_path_to_platform_dir()}/pddf/pddf-device.json"
        with open(json_path) as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        log_error(f"PDDF post-driver-install: could not read pddf-device.json: {e}")
        return set()

    buses = set()
    for dev in data.values():
        if not isinstance(dev, dict):
            continue
        parent_bus = dev.get("i2c", {}).get("topo_info", {}).get("parent_bus")
        if not isinstance(parent_bus, str):
            continue
        try:
            buses.add(int(parent_bus, 0))
        except ValueError:
            continue
    return buses


def wait_for_static_buses(expected_buses):
    if not expected_buses:
        return
    deadline = time.monotonic() + STATIC_BUS_WAIT_SEC
    missing = expected_buses
    while time.monotonic() < deadline:
        udev_settle()
        missing = {b for b in expected_buses
                   if not os.path.exists(f"/sys/bus/i2c/devices/i2c-{b}")}
        if not missing:
            return
        time.sleep(STATIC_BUS_POLL_INTERVAL_SEC)
    log_error(f"PDDF post-driver-install: buses {sorted(missing)} still "
              f"missing after {STATIC_BUS_WAIT_SEC}s")


def wait_for_i2c_adapters_to_stabilize():
    previous_count = count_i2c_adapters()
    stable_checks = 0
    deadline = time.monotonic() + MAX_STABLE_WAIT_SEC
    while time.monotonic() < deadline:
        time.sleep(STABLE_CHECK_INTERVAL_SEC)
        udev_settle()
        current_count = count_i2c_adapters()
        if current_count == previous_count:
            stable_checks += 1
            if stable_checks >= STABLE_CHECKS_REQUIRED:
                return current_count
        else:
            stable_checks = 0
        previous_count = current_count
    log_error(f"PDDF post-driver-install: i2c adapter count "
              f"({previous_count}) did not stabilize within "
              f"{MAX_STABLE_WAIT_SEC}s")
    return previous_count


def main():
    log_info("PDDF post-driver-install: waiting for udev to settle")
    udev_settle()

    static_buses = get_static_parent_buses()
    if static_buses:
        log_info(f"PDDF post-driver-install: waiting for static buses {sorted(static_buses)}")
        wait_for_static_buses(static_buses)

    final_count = wait_for_i2c_adapters_to_stabilize()
    log_info(f"PDDF post-driver-install: udev settled ({final_count} i2c adapters)")


if __name__ == "__main__":
    main()
