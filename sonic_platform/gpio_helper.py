#!/usr/bin/env python3
#
# gpio_helper.py — Shared GPIO utilities for SONiC platform API
#
# Copyright (c) 2026, Hewlett Packard Enterprise Development LP
# All rights reserved.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Generic GPIO helpers for gpiochip-based presence/control detection.
# All platform-specific values (labels, offsets) come from pddf-device.json.
# This module is hardware-agnostic — it works with any gpiochip that
# exports standard Linux GPIO sysfs.

"""
GPIO Helper Module

Provides label-based gpiochip discovery and GPIO read/write via
the Linux /sys/class/gpio sysfs interface.

Usage:
    from sonic_platform.gpio_helper import get_gpiochip_base, read_gpio

    base = get_gpiochip_base("gpio-jnx-i2cs.21-21-56")
    if base is not None:
        value = read_gpio(base + offset)  # returns "0" or "1"
"""

import glob
import os
import re
import syslog

SYSLOG_IDENTIFIER = "gpio_helper"

# Module-level cache: gpiochip label -> base number
# Populated on first call to get_gpiochip_base(), shared across all callers
_gpiochip_cache = None


def _log_err(msg):
    syslog.openlog(SYSLOG_IDENTIFIER)
    syslog.syslog(syslog.LOG_ERR, msg)
    syslog.closelog()


def _scan_gpiochips():
    """Scan all gpiochips and build label->base mapping."""
    cache = {}
    for path in glob.glob("/sys/class/gpio/gpiochip*/label"):
        try:
            with open(path, 'r') as f:
                label = f.read().strip()
            match = re.search(r"gpiochip(\d+)", path)
            if match:
                cache[label] = int(match.group(1))
        except Exception:
            pass
    return cache


def get_gpiochip_base(label):
    """
    Look up gpiochip base number by label string.

    The label is set by the kernel GPIO driver at probe time (e.g.,
    "gpio-jnx-i2cs.21-21-56" for the PDB I2CS GPIO controller).
    Labels are stable across reboots; base numbers are dynamically
    assigned and may change.

    Args:
        label: Gpiochip label string (from /sys/class/gpio/gpiochipN/label)

    Returns:
        int: GPIO base number, or None if label not found
    """
    global _gpiochip_cache
    if _gpiochip_cache is None:
        _gpiochip_cache = _scan_gpiochips()

    base = _gpiochip_cache.get(label)

    # Cache miss — rescan in case the chip was loaded after initial scan
    if base is None:
        _gpiochip_cache = _scan_gpiochips()
        base = _gpiochip_cache.get(label)

    return base


def invalidate_cache():
    """Force re-scan of gpiochips on next get_gpiochip_base() call."""
    global _gpiochip_cache
    _gpiochip_cache = None


# ========================================================================
# Persistent file descriptor cache for GPIO value files
# ========================================================================
#
# Hot-path optimization for SFP presence polling (36 ports x 0.5s cycle).
# Instead of open()/read()/close() per GPIO read (4+ syscalls including
# the export check), maintains open file descriptors and uses
# lseek(0) + read() (2 syscalls).  FDs are opened O_RDWR so a single
# FD serves both read_gpio() and write_gpio().
#
# On I/O error (device removed, driver unbound) the FD is closed and
# the pin is removed from both caches, so the next call re-exports
# and re-opens transparently.

_gpio_fd_cache = {}    # pin (int) -> open fd (int)
_gpio_exported = set() # pins verified as exported in sysfs
_GPIO_VALUE_FMT = "/sys/class/gpio/gpio{}/value"
_GPIO_NAMED_VALUE_FMT = "/sys/class/gpio/{}/value"
_pin_named_path = {}       # pin (int) -> resolved name-based value node (lazy cache)
_pin_named_candidate = {}  # pin (int) -> (label, offset) for lazy name-node derivation


def _gpio_value_path(pin):
    """Return the sysfs 'value' node for a pin.
    Prefers the numeric gpio<N> node (standard sysfs GPIO). Only a name-based node
    is used when numeric node is absent, like controllers that export their lines by name
    """
    numeric = _GPIO_VALUE_FMT.format(pin)
    if os.path.exists(numeric):
        return numeric
    named = _pin_named_path.get(pin)
    if named is None:
        cand = _pin_named_candidate.get(pin)
        if cand is not None:
            label, offset = cand
            parts = label.split('-')
            if len(parts) >= 2:
                named = _GPIO_NAMED_VALUE_FMT.format(
                    "{}{}_{}".format(parts[-2], offset, parts[-1]))
                _pin_named_path[pin] = named
    if named and os.path.exists(named):
        return named
    return None


def _ensure_gpio_exported(pin):
    """Export a GPIO pin if not already done. Returns True on success."""
    if pin in _gpio_exported:
        return True
    if _gpio_value_path(pin) is not None:
        _gpio_exported.add(pin)
        return True
    try:
        with open("/sys/class/gpio/export", 'w') as f:
            f.write(str(pin))
        _gpio_exported.add(pin)
        return True
    except IOError as e:
        if e.errno == 16:  # EBUSY — already exported by another process
            _gpio_exported.add(pin)
            return True
        _log_err("GPIO export failed for pin {}: {}".format(pin, e))
        return False


def _get_gpio_fd(pin):
    """Get or open a persistent FD for a GPIO value file."""
    fd = _gpio_fd_cache.get(pin)
    if fd is not None:
        return fd
    if not _ensure_gpio_exported(pin):
        return None
    path = _gpio_value_path(pin)
    if path is None:
        _log_err("GPIO value node not found for pin {}".format(pin))
        return None
    try:
        fd = os.open(path, os.O_RDWR)
    except OSError:
        try:
            fd = os.open(path, os.O_RDONLY)
        except OSError as e:
            _log_err("GPIO open failed for pin {}: {}".format(pin, e))
            return None
    _gpio_fd_cache[pin] = fd
    return fd


def _release_gpio_fd(pin, fd):
    """Close and remove a cached GPIO FD (called on I/O error)."""
    _gpio_fd_cache.pop(pin, None)
    _gpio_exported.discard(pin)
    try:
        os.close(fd)
    except OSError:
        pass


def read_gpio(pin):
    """
    Read GPIO pin value using a persistent file descriptor.

    Uses lseek(0) + read() on a cached FD instead of open() + read() +
    close(), cutting per-read syscall overhead roughly in half.

    Args:
        pin: GPIO pin number (base + offset)

    Returns:
        str: "0" or "1", or None on error
    """
    fd = _get_gpio_fd(pin)
    if fd is None:
        return None
    try:
        # pread is a single atomic syscall — no shared file-position race
        # when the polling thread and SFP worker thread both read the same
        # presence pin concurrently via a shared FD.
        data = os.pread(fd, 4, 0)
        return data.decode('ascii', errors='ignore').strip()
    except OSError as e:
        _release_gpio_fd(pin, fd)
        _log_err("GPIO read failed for pin {}: {}".format(pin, e))
        return None


def resolve_gpio_pin(label, offset):
    """
    Resolve a gpiochip label + offset to an absolute GPIO pin number.

    Convenience wrapper around get_gpiochip_base() that handles the common
    pattern of label lookup + offset addition used by psu.py, fan.py, sfp.py.

    Args:
        label:  Gpiochip label string (e.g., "gpio-jnx-i2cs.21-21-56")
        offset: Integer offset within the gpiochip

    Returns:
        int: Absolute GPIO pin number, or None if label not found
    """
    if not label:
        return None
    base = get_gpiochip_base(label)
    if base is None:
        return None
    pin = base + int(offset)
    # Some controllers export their lines under a name-based node
    # Record the label+offset only as a *candidate*
    _pin_named_candidate[pin] = (label, offset)
    return pin


def read_gpio_bool(pin, active_value="1"):
    """
    Read a GPIO pin and return a boolean based on active value.

    Convenience wrapper for the common pattern:
        read_gpio(pin) == active_value

    Args:
        pin:          Absolute GPIO pin number (or None)
        active_value: The string value ("0" or "1") that means True

    Returns:
        bool: True if pin reads as active_value, False otherwise
              (including when pin is None)
    """
    if pin is None:
        return False
    val = read_gpio(pin)
    return val == active_value


def write_gpio(pin, value):
    """
    Write GPIO pin value using a persistent file descriptor.

    Args:
        pin: GPIO pin number (base + offset)
        value: 0 or 1

    Returns:
        bool: True on success, False on error
    """
    fd = _get_gpio_fd(pin)
    if fd is None:
        return False
    try:
        # pwrite is atomic w.r.t. file position (same rationale as pread)
        os.pwrite(fd, str(value).encode(), 0)
        return True
    except OSError as e:
        _release_gpio_fd(pin, fd)
        _log_err("GPIO write failed for pin {}: {}".format(pin, e))
        return False


def close_all_gpio_fds():
    """Close all cached GPIO file descriptors.

    Call during shutdown or when GPIO topology changes (driver reload).
    Next read_gpio/write_gpio call will re-export and re-open.
    """
    global _gpio_fd_cache, _gpio_exported
    for fd in _gpio_fd_cache.values():
        try:
            os.close(fd)
        except OSError:
            pass
    _gpio_fd_cache = {}
    _gpio_exported = set()
