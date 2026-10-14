#!/usr/bin/env python3
#
# sysfs_util.py — Shared sysfs, hwmon, and I2C bus discovery utilities
#
# Copyright (c) 2026, Hewlett Packard Enterprise Development LP
# All rights reserved.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Consolidates common sysfs read/write, hwmon device lookup, and I2C bus
# discovery code that was previously duplicated across fan.py, sfp.py,
# and voltage_sensor.py.  All functions are hardware-agnostic.
#
# To support a new platform, no changes needed here — only JSON changes.

"""
Sysfs Utility Module

Provides:
  - sysfs_read_int / sysfs_write:  Generic sysfs integer read/write
  - find_hwmon_by_name:            Discover hwmon path by driver name
  - find_hwmon_by_i2c:             Discover hwmon path by I2C device path
  - find_i2c_bus:                  Find I2C bus number by adapter name (cached)
  - find_i2c_bus_mux:              Find bus through 1- or 2-level MUX chain

Usage:
    from sonic_platform.sysfs_util import sysfs_read_int, find_i2c_bus
"""

import glob
import os
import re
import syslog

SYSLOG_IDENTIFIER = "sysfs_util"

# ============================================================================
#  Logging (single shared instance for this module)
# ============================================================================

def _log_err(msg):
    syslog.openlog(SYSLOG_IDENTIFIER)
    syslog.syslog(syslog.LOG_ERR, msg)
    syslog.closelog()


def _log_info(msg):
    syslog.openlog(SYSLOG_IDENTIFIER)
    syslog.syslog(syslog.LOG_INFO, msg)
    syslog.closelog()


# ============================================================================
#  Sysfs generic read / write
# ============================================================================

def sysfs_read_int(path):
    """Read an integer value from a sysfs file.

    Uses os.open/read/close instead of Python buffered I/O to avoid
    TextIOWrapper + BufferedReader + FileIO object allocation overhead
    on every call.  For small sysfs reads (1-10 bytes) this is ~1.5-2x
    faster.

    Args:
        path: Absolute path to sysfs attribute file.

    Returns:
        int value on success, None on failure (file missing, non-integer, etc.)
    """
    try:
        fd = os.open(path, os.O_RDONLY)
        try:
            data = os.read(fd, 32)
            return int(data.strip().decode())
        finally:
            os.close(fd)
    except (OSError, ValueError):
        return None


def sysfs_write(path, value):
    """Write a value to a sysfs file.

    Uses os.open/write/close to match sysfs_read_int's low-overhead
    approach.

    Args:
        path:  Absolute path to sysfs attribute file.
        value: Value to write (converted to str).

    Returns:
        True on success, False on failure.
    """
    try:
        fd = os.open(path, os.O_WRONLY)
        try:
            os.write(fd, str(value).encode())
        finally:
            os.close(fd)
        return True
    except OSError:
        return False


# ============================================================================
#  Hwmon discovery
# ============================================================================

# Module-level cache: hwmon driver name -> sysfs path
_hwmon_name_cache = {}


def find_hwmon_by_name(hwmon_name):
    """Find hwmon sysfs directory by driver name (cached).

    Scans /sys/class/hwmon/hwmon*/name until a match is found.

    Args:
        hwmon_name: The 'name' attribute of the hwmon device
                    (e.g., "i2cs_fan", "tps53659").

    Returns:
        str: Path to hwmon directory (e.g., /sys/class/hwmon/hwmon3),
             or None if not found.
    """
    if not hwmon_name:
        return None

    if hwmon_name in _hwmon_name_cache:
        cached = _hwmon_name_cache[hwmon_name]
        # Verify cached path is still valid
        if os.path.isdir(cached):
            return cached
        del _hwmon_name_cache[hwmon_name]

    for hwmon_dir in glob.glob("/sys/class/hwmon/hwmon*"):
        name_path = os.path.join(hwmon_dir, "name")
        if os.path.exists(name_path):
            try:
                with open(name_path) as f:
                    if f.read().strip() == hwmon_name:
                        _hwmon_name_cache[hwmon_name] = hwmon_dir
                        return hwmon_dir
            except IOError:
                continue
    return None


# Module-level cache: I2C device path -> hwmon path
_hwmon_i2c_cache = {}


def find_hwmon_by_i2c(i2c_device_path):
    """Find hwmon sysfs directory under an I2C device (cached).

    Looks for {i2c_device_path}/hwmon/hwmon* subdirectories.
    Results are cached for the lifetime of the process (hwmon
    numbering doesn't change at runtime after device probe).

    Args:
        i2c_device_path: Absolute path to I2C device sysfs directory
                         (e.g., /sys/bus/i2c/devices/75-005d).

    Returns:
        str: Path to first hwmon directory found, or None.
    """
    if i2c_device_path in _hwmon_i2c_cache:
        cached = _hwmon_i2c_cache[i2c_device_path]
        if os.path.isdir(cached):
            return cached
        del _hwmon_i2c_cache[i2c_device_path]

    hwmon_glob = os.path.join(i2c_device_path, 'hwmon', 'hwmon*')
    hwmon_dirs = glob.glob(hwmon_glob)
    if hwmon_dirs:
        _hwmon_i2c_cache[i2c_device_path] = hwmon_dirs[0]
        return hwmon_dirs[0]
    return None


# ============================================================================
#  I2C bus discovery
# ============================================================================

_I2C_DEVICES_PATH = "/sys/bus/i2c/devices"

# Module-level cache: adapter_name -> bus number
_i2c_bus_cache = {}

# Module-level cache: PCI path -> TMC base bus number
_tmc_bus_cache = {}


def find_i2c_tmc_bus(pci_path):
    """Find the TMC I2C adapter base bus number via PCI sysfs path (cached).

    The TMC MFD driver creates an i2c-tmc platform device under the PCI
    device.  The adapter bus number is dynamically assigned, so we discover
    it by scanning {pci_path}/i2c-tmc.*/i2c-*.

    Args:
        pci_path: PCI device sysfs path, e.g. "/sys/bus/pci/devices/0000:0d:00.0"

    Returns:
        int: Bus number (>=0) on success, or None if not found.
    """
    if pci_path in _tmc_bus_cache:
        return _tmc_bus_cache[pci_path]

    for adapter_dir in sorted(glob.glob(os.path.join(pci_path, 'i2c-tmc.*/i2c-*'))):
        try:
            bus = int(os.path.basename(adapter_dir).split('-')[1])
            _tmc_bus_cache[pci_path] = bus
            return bus
        except (ValueError, IndexError):
            continue

    return None


def find_i2c_bus(adapter_name):
    """Find I2C bus number by adapter name string (cached).

    Scans /sys/bus/i2c/devices/i2c-*/name until a match is found.
    Results are cached for the lifetime of the process (I2C topology
    doesn't change at runtime after platform init).

    Args:
        adapter_name: The I2C adapter name to search for
                      (e.g., "i2c-supercon.21:5", "i2c-42-mux (chan_id 0)").

    Returns:
        int: Bus number (>=0) on success, or None if not found.
    """
    if adapter_name in _i2c_bus_cache:
        return _i2c_bus_cache[adapter_name]

    if not os.path.isdir(_I2C_DEVICES_PATH):
        return None

    i2c_re = re.compile(r'^i2c-(\d+)$')

    try:
        for entry in os.listdir(_I2C_DEVICES_PATH):
            m = i2c_re.match(entry)
            if not m:
                continue
            name_file = os.path.join(_I2C_DEVICES_PATH, entry, "name")
            try:
                with open(name_file, 'r') as f:
                    if f.read().strip() == adapter_name:
                        bus = int(m.group(1))
                        _i2c_bus_cache[adapter_name] = bus
                        return bus
            except (IOError, OSError):
                continue
    except OSError:
        pass

    return None


def find_i2c_bus_mux(adapter_name, mux_chan='', mux2_chan='',
                     mux2_addr=''):
    """Find I2C bus number through 1- or 2-level MUX chain.

    Traverses I2C MUX topology step by step:
      1. Find master adapter bus by name
      2. Optionally traverse first MUX channel
      3. Optionally traverse second (cascaded) MUX channel

    When mux2_addr is specified, the second-level MUX is resolved via its
    sysfs device path (channel-N symlink) instead of name matching.  This
    correctly disambiguates when multiple MUXes share the same parent bus
    (e.g., PCA9548 @0x70 and @0x71 both on fpci2c ch0).  If the MUX
    device does not exist yet, it is auto-created as a pca9548.

    Args:
        adapter_name: Master I2C adapter name (e.g., "i2c-supercon.2:1").
        mux_chan:      First MUX channel ID (e.g., "0"). Empty = no MUX.
        mux2_chan:     Second MUX channel ID. Empty = no second MUX.
        mux2_addr:    I2C address of the second MUX (e.g., "0x70").
                      When set, uses sysfs channel-N path for disambiguation.

    Returns:
        int: Final bus number, or None if any level not found.
    """
    # Level 0: master adapter
    parent_bus = find_i2c_bus(adapter_name)
    if parent_bus is None:
        return None

    if not mux_chan:
        return parent_bus

    # Level 1: first MUX channel
    mux1_name = 'i2c-{}-mux (chan_id {})'.format(parent_bus, mux_chan)
    mux1_bus = find_i2c_bus(mux1_name)
    if mux1_bus is None:
        return None

    if not mux2_chan:
        return mux1_bus

    # Level 2: second (cascaded) MUX channel
    if mux2_addr:
        return _find_mux_channel_bus(mux1_bus, int(mux2_addr, 0),
                                     int(mux2_chan))
    mux2_name = 'i2c-{}-mux (chan_id {})'.format(mux1_bus, mux2_chan)
    return find_i2c_bus(mux2_name)


def _find_mux_channel_bus(parent_bus, mux_addr, channel):
    """Find bus number for a specific MUX device's channel via sysfs.

    Uses /sys/bus/i2c/devices/{bus}-{addr:04x}/channel-{N} symlink to
    resolve the child bus unambiguously.  Works when multiple MUXes
    exist on the same parent bus (e.g., PCA9548 @0x70 and @0x71).

    Auto-creates the MUX device (pca9548) if not present in sysfs.

    Args:
        parent_bus: Parent I2C bus number.
        mux_addr:   I2C address of the MUX device (integer).
        channel:    MUX channel number (integer).

    Returns:
        int: Child bus number, or None if not found.
    """

    if not (
        isinstance(parent_bus, int) and parent_bus >= 0 and
        isinstance(mux_addr, int) and 0x03 <= mux_addr <= 0x77 and
        isinstance(channel, int) and channel >=0
    ):
        _log_err("Invalid input parameters parent_bus:{}, mux_addr:{}, channel:{}".format(parent_bus, mux_addr, channel))

    mux_path = '/sys/bus/i2c/devices/{}-{:04x}'.format(parent_bus, mux_addr)

    # Auto-instantiate MUX if it doesn't exist
    if not os.path.isdir(mux_path):
        _create_i2c_device(parent_bus, mux_addr, 'pca9548')
        if not os.path.isdir(mux_path):
            _log_err("Failed to create MUX pca9548 at {}-{:04x}".format(
                parent_bus, mux_addr))
            return None

    chan_link = os.path.join(mux_path, 'channel-{}'.format(channel))
    if not os.path.islink(chan_link):
        _log_err("MUX channel symlink missing: {}".format(chan_link))
        return None

    # channel-N symlink -> ../../i2c-317
    target = os.path.basename(os.readlink(chan_link))
    m = re.match(r'i2c-(\d+)', target)
    if m:
        bus = int(m.group(1))
        # Cache for future lookups
        _i2c_bus_cache['i2c-{}-mux (chan_id {})'.format(
            parent_bus, channel)] = bus
        return bus
    return None


def _create_i2c_device(bus, addr, driver):
    """Create I2C device via new_device sysfs interface.

    Args:
        bus:    I2C bus number.
        addr:   I2C device address (integer).
        driver: Driver name to bind (e.g., 'pca9548', 'max16602').

    Returns:
        True on success, False on failure.
    """

    valid = (
        isinstance(bus, int) and bus >= 0 and
        isinstance(addr, int) and 0x03 <= addr <= 0x77 and
        isinstance(driver, str) and driver.strip() and
        re.match(r'^[a-zA-Z0-9_\-]+$', driver)
    )

    if not valid:
        _log_err("Invalid input parameters bus:{}, addr:{}, driver:{}".format(bus, addr, driver))
        return False

    import time as _time
    new_device = '/sys/bus/i2c/devices/i2c-{}/new_device'.format(bus)
    if not os.path.exists(new_device):
        _log_err("Cannot create device: bus i2c-{} not found".format(bus))
        return False
    try:
        with open(new_device, 'w') as f:
            f.write('{} 0x{:02x}\n'.format(driver, addr))
        _time.sleep(0.5)
        _log_info("Created {} at {}-{:04x}".format(driver, bus, addr))
        invalidate_i2c_cache()
        return True
    except OSError as e:
        if e.errno != 16:  # EBUSY = device already exists
            _log_err("Failed to create {} at {}-{:04x}: {}".format(
                driver, bus, addr, e))
        return e.errno == 16  # EBUSY is not a failure


def invalidate_i2c_cache():
    """Clear the I2C bus lookup cache.  Useful if topology changes."""
    global _i2c_bus_cache
    _i2c_bus_cache = {}
