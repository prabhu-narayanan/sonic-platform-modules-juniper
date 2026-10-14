#!/usr/bin/env python3
#
# override.py — generic per-platform implementation loader.
#
# Copyright (c) 2026, Juniper Networks, Inc.
# All rights reserved.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Loads optional per-platform override classes from the running platform's
# device directory and returns them by kind. Contains no platform/model names.
#
# Layout: each device type has its OWN override file under
#   <platform_dir>/pddf/platform_impl/<snake(kind)>.py
# defining a class named after the kind, e.g.
#   <platform_dir>/pddf/platform_impl/sfp.py           -> class Sfp(SfpImplBase)
#   <platform_dir>/pddf/platform_impl/reboot_cause.py  -> class RebootCause(...)
# A platform ships only the files it needs. If a platform ships no override for a
# kind, the shared sonic_platform.impl_base.<kind>ImplBase default is used, so
# behavior is unchanged.
#
# Writing an override (source lives in <platform>/platform_impl/<kind>.py):
#   from sonic_platform.impl_base import ChassisImplBase
#   class Chassis(ChassisImplBase):        # class name == kind
#       def get_reboot_cause(self):        # override only what differs
#           val = self._devmem_read(0x...) # inherited Impl mechanics via self
#           ...                            # framework state via self._host
# Ship the file via debian/rules (platform_impl/ is copied into pddf/); the
# rest of the device's behavior stays on the shared <kind>ImplBase default.

import importlib.util
import functools
import os
import re
import syslog


@functools.lru_cache(maxsize=1)
def _impl_dir():
    """Return <platform_dir>/pddf/platform_impl directory once, or None."""
    try:
        from sonic_py_common import device_info
        path = os.path.join(
            device_info.get_path_to_platform_dir(), "pddf", "platform_impl")
        return path if os.path.isdir(path) else None
    except Exception:
        return None


def _snake(kind):
    """Sfp -> sfp, AsicThermal -> asic_thermal, VoltageSensor -> voltage_sensor."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", kind).lower()


@functools.lru_cache(maxsize=None)
def _override_class(kind):
    """Import <platform_dir>/pddf/platform_impl/<kind>.py once and return its
    class `kind`, or None when the platform ships no override for this kind.

    The module filename is the snake_case of `kind` (Sfp -> sfp.py); the
    all-lowercase form (kind.lower() + ".py") is also accepted.
    """
    base = _impl_dir()
    if not base:
        return None
    for fname in (_snake(kind) + ".py", kind.lower() + ".py"):
        path = os.path.join(base, fname)
        if not os.path.exists(path):
            continue
        try:
            spec = importlib.util.spec_from_file_location(
                "platform_impl_" + kind, path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return getattr(mod, kind, None)
        except Exception as e:
            syslog.syslog(syslog.LOG_ERR,
                          "override: failed to load {} from {}: {}".format(kind, path, e))
            return None
    return None


def load_impl(kind, host=None):
    """Return an instance of the platform override class `kind`, else the base.

    `kind` is e.g. "Sfp", "Chassis", "Psu". Looks for a per-platform override at
    <platform_dir>/pddf/platform_impl/<kind>.py defining a class named `kind`;
    falls back to sonic_platform.impl_base.<kind>ImplBase. When `host` is given
    it is passed to the impl constructor (the impl holds a back-reference to its
    owning device object).
    """
    cls = _override_class(kind)
    if cls is None:
        import sonic_platform.impl_base as base
        cls = getattr(base, kind + "ImplBase")
    return cls(host) if host is not None else cls()
