#!/usr/bin/env python3
#
# impl_base/psu.py — default PSU platform implementation.
#
# Copyright (c) 2026, Juniper Networks, Inc.
# All rights reserved.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# PsuImplBase holds the inherited PSU public API only. State, config parsing,
# and the sysfs/EEPROM/GPIO mechanics live on the Psu facade (self._host);
# framework fallbacks call PddfPsu.X(self._host). Platforms override only the
# methods that differ.

import os
import glob

try:
    from sonic_platform_pddf_base.pddf_psu import PddfPsu
except ImportError as e:
    raise ImportError("%s - required module not found" % e)

# PSU IDEEPROM field offsets (24c02 at I2C 0x50)
_EEPROM_REVISION_OFFSET = 0x08
_EEPROM_REVISION_LEN = 8
_EEPROM_SERIAL_OFFSET = 0x20
_EEPROM_SERIAL_LEN = 12

# Glob pattern for garnet-psu platform device (bus number varies per system)
_GARNET_PSU_GLOB = "/sys/bus/platform/devices/garnet-psu.*/psu{}_present"


class PsuImplBase:
    """Default per-platform PSU implementation (inherited public API only).

    State, config parsing, and mechanics live on the Psu facade (self._host);
    framework fallbacks call PddfPsu.X(self._host). Platforms override only the
    methods that differ.
    """

    def __init__(self, host):
        self._host = host

    # ------------------------------------------------------------------ #
    #  Presence: garnet-psu platform sysfs or EEPROM probe
    # ------------------------------------------------------------------ #
    def get_presence(self):
        host = self._host
        gpio_presence = host._read_presence_gpio()
        if gpio_presence is not None:
            # A PSU seated after a boot with its bay empty is reported by the
            # GPIO, but its IDEEPROM client is still unbound; re-bind it so
            # model/serial/revision can be read.
            if gpio_presence and host._ideeprom_authoritative:
                host._recover_eeprom()
            return host._note_presence(gpio_presence)

        # psu_index is 1-based; driver uses 0-based (psu0_present, psu1_present)
        pattern = _GARNET_PSU_GLOB.format(host.psu_index - 1)
        paths = glob.glob(pattern)
        if paths:
            try:
                with open(paths[0], 'r') as f:
                    return host._note_presence(f.read().strip() == '1')
            except (OSError, IOError):
                pass

        # Try GPIO-based presence (from PDDF base).  A descriptor whose
        # psu_present attr does not resolve to a GPIO node makes the base
        # raise (KeyError: 'attr_devname'), so treat any failure as "not
        # detected" and fall through -- a platform API getter must not raise.
        try:
            gpio_result = PddfPsu.get_presence(host)
        except Exception:
            gpio_result = False
        if gpio_result or not host._ideeprom_authoritative:
            return host._note_presence(gpio_result)

        # EEPROM-based fallback: a successful IDEEPROM read means the PSU is
        # physically present.  If at24 is unbound (boot with the bay empty)
        # but the chip answers, re-bind it and read again.
        present = host._read_eeprom(0, 1) is not None
        if not present and host._recover_eeprom():
            present = host._read_eeprom(0, 1) is not None
        return host._note_presence(present)

    # ------------------------------------------------------------------ #
    #  Model: EEPROM @ 0x4F (20 bytes), fallback to PDDF PMBus
    # ------------------------------------------------------------------ #
    def get_model(self):
        host = self._host
        if host._model_cache is not None:
            return host._model_cache

        if not host.get_presence():
            host._model_cache = None
            return 'N/A'

        if host._ideeprom_authoritative:
            data = host._read_eeprom(0x4F, 20)
            if data:
                try:
                    model = data.split(b'\x00')[0].split(b'\xff')[0] \
                                .decode('ascii', errors='ignore').strip()
                    if model:
                        host._model_cache = model
                        return model
                except Exception:
                    pass
        result = PddfPsu.get_model(host)
        if result and result.strip():
            host._model_cache = result
            return result
        return 'N/A'

    # ------------------------------------------------------------------ #
    #  V/I/P: PMBus hwmon (opt-in via pmbus_hwmon in pddf-device.json)
    # ------------------------------------------------------------------ #
    def get_voltage(self):
        host = self._host
        v = host._read_pmbus_hwmon('in', ('vout1', 'vout'), 1000.0)
        if v is not None:
            return round(v, 2)
        return PddfPsu.get_voltage(host)

    def get_current(self):
        host = self._host
        i = host._read_pmbus_hwmon('curr', ('iout1', 'iout'), 1000.0)
        if i is not None:
            return round(i, 2)
        return PddfPsu.get_current(host)

    def get_power(self):
        host = self._host
        p = host._read_pmbus_hwmon('power', ('pout1', 'pout'), 1000000.0)
        if p is not None:
            return round(p, 2)
        p = PddfPsu.get_power(host)
        if p:
            return p

        # PSUs with no readable output-power register report it as 0; derive it
        # from V x I instead, as the Junos PEM driver does.
        voltage = host.get_voltage()
        current = host.get_current()
        if voltage and current:
            return round(voltage * current, 2)
        return p

    def get_input_voltage(self):
        host = self._host
        v = host._read_pmbus_hwmon('in', ('vin',), 1000.0)
        if v is not None:
            return round(v, 2)
        return PddfPsu.get_input_voltage(host)

    def get_input_current(self):
        host = self._host
        i = host._read_pmbus_hwmon('curr', ('iin',), 1000.0)
        if i is not None:
            return round(i, 2)
        return PddfPsu.get_input_current(host)

    def get_input_power(self):
        host = self._host
        p = host._read_pmbus_hwmon('power', ('pin',), 1000000.0)
        if p is not None:
            return round(p, 2)
        return PddfPsu.get_input_power(host)

    # ------------------------------------------------------------------ #
    #  Power-good: derived from output voltage (no dedicated GPIO)
    # ------------------------------------------------------------------ #
    def get_powergood_status(self):
        host = self._host
        if not host.get_presence():
            return False
        try:
            voltage = host.get_voltage()
            return voltage is not None and voltage > 0.0
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    #  Serial: EEPROM @ 0x20 (12 bytes), fallback to PDDF PMBus
    # ------------------------------------------------------------------ #
    def get_serial(self):
        host = self._host
        if host._serial_cache is not None:
            return host._serial_cache

        if not host.get_presence():
            host._serial_cache = None
            return 'N/A'

        data = host._read_eeprom(_EEPROM_SERIAL_OFFSET, _EEPROM_SERIAL_LEN)
        if data:
            try:
                serial = data.decode('ascii', errors='ignore').rstrip('\x00').strip()
                if serial and serial != '\xff' * len(serial):
                    host._serial_cache = serial
                    return serial
            except Exception:
                pass

        # Fallback to PDDF (PMBus MFR_SERIAL)
        result = PddfPsu.get_serial(host)
        if result and result.strip():
            host._serial_cache = result
            return result

        return 'N/A'

    # ------------------------------------------------------------------ #
    #  Revision: EEPROM @ 0x08 (8 bytes, e.g. "REV 09")
    # ------------------------------------------------------------------ #
    def get_revision(self):
        host = self._host
        if host._revision_cache is not None:
            return host._revision_cache

        if not host.get_presence():
            host._revision_cache = None
            return 'N/A'

        data = host._read_eeprom(_EEPROM_REVISION_OFFSET, _EEPROM_REVISION_LEN)
        if data:
            try:
                revision = data.decode('ascii', errors='ignore').rstrip('\x00').strip()
                if revision and revision != '\xff' * len(revision):
                    host._revision_cache = revision
                    return revision
            except Exception:
                pass

        return 'N/A'

    def is_replaceable(self):
        return self._host._is_replaceable

    def get_voltage_high_threshold(self):
        host = self._host
        if host._voltage_high_threshold is not None:
            return host._voltage_high_threshold
        return PddfPsu.get_voltage_high_threshold(host)

    def get_voltage_low_threshold(self):
        host = self._host
        if host._voltage_low_threshold is not None:
            return host._voltage_low_threshold
        return PddfPsu.get_voltage_low_threshold(host)
