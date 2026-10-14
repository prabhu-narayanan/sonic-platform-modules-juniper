#!/usr/bin/env python3
#
# psu.py — PDDF PSU wrapper for SONiC Platform API
#
# Copyright (c) 2026, Juniper Networks, Inc.
# All rights reserved.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Extends PddfPsu. PSU presence is read from the garnet-psu platform driver
# sysfs files instead of GPIO, because the QFX5241-64 (garnet64) FPGA exposes
# PSU presence via a dedicated platform device — not via a gpiochip:
#
#   /sys/bus/platform/devices/garnet-psu.*/psu{N}_present
#     where N = psu_index - 1  (0-based)
#
# Serial number and HW revision are read from the PSU IDEEPROM (24c02 at
# I2C address 0x50).  The EEPROM layout:
#   0x08  8 bytes  — Revision string
#   0x20 12 bytes  — Serial number

import os
import fcntl
import glob
import syslog
import time

from sonic_platform.pmbus_raw import resolve_i2c_bus

try:
    from sonic_platform_pddf_base.pddf_psu import PddfPsu
    from sonic_platform.gpio_helper import read_gpio_bool, resolve_gpio_pin
except ImportError as e:
    raise ImportError("%s - required module not found" % e)

# PSU IDEEPROM field offsets (24c02 at I2C 0x50)
_EEPROM_REVISION_OFFSET = 0x08
_EEPROM_REVISION_LEN = 8
_EEPROM_SERIAL_OFFSET = 0x20
_EEPROM_SERIAL_LEN = 12

# Fallback IDEEPROM re-probe interval, used only when /dev/i2c-<bus> is not
# available so the bay cannot be probed directly.  Deliberately long: a re-probe
# tears down and re-creates an I2C client, and every process holding the
# platform API (psud, psuStatusd, ...) runs this independently.
_I2C_REPROBE_INTERVAL_SECS = 60.0

# ioctl to bind an /dev/i2c-N fd to a slave address even if a driver is bound.
_I2C_SLAVE_FORCE = 0x0706

# Glob pattern for garnet-psu platform device (bus number varies per system)
_GARNET_PSU_GLOB = "/sys/bus/platform/devices/garnet-psu.*/psu{}_present"

def _opt_float(value):
    """float(value), or None when the attribute is absent or malformed."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# =============================================================================
# PddfPsu Wrapper
# =============================================================================

class Psu(PddfPsu):
    """PDDF PSU wrapper with garnet-psu platform presence + EEPROM serial/revision."""

    def __init__(self, index, pddf_data=None, pddf_plugin_data=None):
        PddfPsu.__init__(self, index, pddf_data, pddf_plugin_data)

        self._eeprom_path = None
        self._eeprom_bus = None
        self._eeprom_addr = None
        self._eeprom_client_name = None
        self._present = False
        self._last_reprobe = None
        self._serial_cache = None
        self._revision_cache = None
        self._model_cache = None
        self._pmbus_i2c_dir = None
        self._ideeprom_authoritative = False
        self._presence_gpio_label = ''
        self._presence_gpio_offset = 0
        self._presence_gpio_active = '1'
        self._presence_gpio_pin = None
        self._is_replaceable = True
        self._voltage_high_threshold = None
        self._voltage_low_threshold = None

        from sonic_platform.override import load_impl
        self._impl = load_impl("Psu", self)
        # Locate the PSU EEPROM sysfs path from PSU{N}_EEPROM JSON entry.
        # Resolve it unconditionally: the at24 'eeprom' node only appears once
        # the driver has bound, which cannot happen while the bay is empty, so
        # gating on its existence here would pin the path to None for the whole
        # lifetime of the object and no later insertion could ever be read.
        eeprom_key = "PSU{}_EEPROM".format(self.psu_index)
        if pddf_data and eeprom_key in pddf_data.data:
            topo = pddf_data.data[eeprom_key].get('i2c', {}).get('topo_info', {})
            bus = resolve_i2c_bus(pddf_data, topo.get('parent_bus', '0'))
            addr = int(topo.get('dev_addr', '0'), 0)
            self._eeprom_bus = bus
            self._eeprom_addr = addr
            self._eeprom_path = '/sys/bus/i2c/devices/{}-{:04x}/eeprom'.format(bus, addr)
            # OPT-IN: trust IDEEPROM for presence + model (QFX5220 and similar)
            dev_attr = pddf_data.data[eeprom_key].get('i2c', {}).get('dev_attr', {})
            self._ideeprom_authoritative = (
                str(dev_attr.get('ideeprom_authoritative', '0')) == '1')

        # The flag is conventionally carried on the PSU entry rather than on
        # PSU{N}_EEPROM; accept it from either place.
        psu_key = "PSU{}".format(self.psu_index)
        if pddf_data and psu_key in pddf_data.data:
            psu_attr = pddf_data.data[psu_key].get('dev_attr', {})
            if not self._ideeprom_authoritative:
                self._ideeprom_authoritative = (
                    str(psu_attr.get('ideeprom_authoritative', '0')) == '1')

            # Presence from a gpiochip line whenever the PSU entry names one.
            self._presence_gpio_label = psu_attr.get('gpio_label', '')
            if self._presence_gpio_label:
                self._presence_gpio_offset = int(
                    psu_attr.get('gpio_presence_offset', 0))
                self._presence_gpio_active = str(
                    psu_attr.get('gpio_active_value', '1'))

            self._is_replaceable = str(psu_attr.get('is_replaceable', '1')) == '1'

            # Static output-voltage limits for PSUs whose PMBus MFR_VOUT_MIN/MAX
            # registers are unimplemented; unset -> PDDF/PMBus stays in charge.
            self._voltage_high_threshold = _opt_float(
                psu_attr.get('voltage_high_threshold'))
            self._voltage_low_threshold = _opt_float(
                psu_attr.get('voltage_low_threshold'))

        # OPT-IN: locate PSU PMBus hwmon dir for direct V/I/P/temp reads.
        # Only enabled when PSU{N}_PMBUS dev_attr sets "pmbus_hwmon": "1".
        pmbus_key = "PSU{}_PMBUS".format(self.psu_index)
        if pddf_data and pmbus_key in pddf_data.data:
            pmbus_i2c = pddf_data.data[pmbus_key].get('i2c', {})
            if str(pmbus_i2c.get('dev_attr', {}).get('pmbus_hwmon', '0')) == '1':
                topo = pmbus_i2c.get('topo_info', {})
                bus = resolve_i2c_bus(pddf_data, topo.get('parent_bus', '0'))
                addr = int(topo.get('dev_addr', '0'), 0)
                self._pmbus_i2c_dir = '/sys/bus/i2c/devices/{}-{:04x}'.format(bus, addr)

        # Prime the IDEEPROM client name while the bus is still in its boot state.
        if self._eeprom_bus is not None:
            self._client_name()

    # ------------------------------------------------------------------ #
    #  Hot-insert recovery: re-bind the PSU IDEEPROM client
    # ------------------------------------------------------------------ #
    def _client_name(self):
        """I2C client name of the IDEEPROM node, remembered across re-probes.

        Taken from sysfs and cached, because a re-probe deletes the client
        before re-adding it -- if the re-add failed, sysfs could no longer
        name it and nothing would ever be able to re-create it.
        """
        try:
            with open('/sys/bus/i2c/devices/{}-{:04x}/name'.format(
                    self._eeprom_bus, self._eeprom_addr)) as f:
                self._eeprom_client_name = f.read().strip()
        except OSError:
            pass
        return self._eeprom_client_name

    def _reprobe_eeprom_client(self):
        """Re-run the at24 probe for the IDEEPROM client.

        A client instantiated while its bay was empty stays registered but
        unbound (its probe read is NAKed), and the kernel never retries the
        probe, so the 'eeprom' node never appears once the PSU is inserted.
        Deleting and re-adding the client re-runs the probe.  Only the
        IDEEPROM is handled: the PMBus client at 0x58 is owned by the PDDF PSU
        driver, whose probe must not be re-run by hand.
        """
        name = self._client_name()
        if not name:
            syslog.syslog(syslog.LOG_WARNING,
                          "PSU{}: no I2C client name known for {}-{:04x}, "
                          "cannot re-probe".format(self.psu_index,
                                                   self._eeprom_bus,
                                                   self._eeprom_addr))
            return

        adapter = '/sys/bus/i2c/devices/i2c-{}'.format(self._eeprom_bus)
        try:
            with open(os.path.join(adapter, 'delete_device'), 'w') as f:
                f.write('0x{:02x}'.format(self._eeprom_addr))
        except OSError:
            pass                        # nothing registered at that address

        try:
            with open(os.path.join(adapter, 'new_device'), 'w') as f:
                f.write('{} 0x{:02x}'.format(name, self._eeprom_addr))
        except OSError as e:
            syslog.syslog(syslog.LOG_WARNING,
                          "PSU{}: re-probe of '{} 0x{:02x}' on i2c-{} failed: "
                          "{}".format(self.psu_index, name, self._eeprom_addr,
                                      self._eeprom_bus, e))

    def _bay_occupied(self):
        """True/False if the IDEEPROM ACKs a raw I2C read, None if unknowable.

        Goes straight at /dev/i2c-<bus>, so it reports whether the chip is
        physically answering regardless of whether at24 is bound, and without
        creating or destroying any I2C client.
        """
        if self._eeprom_bus is None:
            return None
        try:
            fd = os.open('/dev/i2c-{}'.format(self._eeprom_bus), os.O_RDWR)
        except OSError:
            return None
        try:
            fcntl.ioctl(fd, _I2C_SLAVE_FORCE, self._eeprom_addr)
            os.read(fd, 1)
            return True
        except OSError:
            return False
        finally:
            os.close(fd)

    def _recover_eeprom(self):
        """Re-bind the IDEEPROM client when the chip answers but at24 is unbound.

        That is the state a boot with an empty bay leaves behind.

        Returns:
            bool: True if a re-probe was attempted, so the caller should re-read.
        """
        if not self._eeprom_path or os.path.isfile(self._eeprom_path):
            return False

        occupied = self._bay_occupied()
        if occupied is False:
            return False            # nothing answering; nothing to re-probe

        if occupied is None:
            # No i2c-dev node, so occupancy is unknowable without a re-probe.
            # Fall back to the throttled blind retry.
            now = time.monotonic()
            if (self._last_reprobe is not None and
                    now - self._last_reprobe < _I2C_REPROBE_INTERVAL_SECS):
                return False
            self._last_reprobe = now

        self._reprobe_eeprom_client()
        return True

    def _note_presence(self, present):
        """Track presence transitions and drop the FRU caches on insertion."""
        if present and not self._present:
            self._serial_cache = None
            self._revision_cache = None
            self._model_cache = None
        self._present = present
        return present

    # ------------------------------------------------------------------ #
    #  EEPROM helper: read N bytes at offset from the 24c02 sysfs file
    # ------------------------------------------------------------------ #
    def _read_eeprom(self, offset, length):
        """Read *length* bytes at *offset* from the PSU IDEEPROM.

        Returns a bytes object, or None on failure.
        """
        if not self._eeprom_path:
            return None
        try:
            with open(self._eeprom_path, 'rb') as f:
                f.seek(offset)
                data = f.read(length)
            return data if len(data) == length else None
        except (OSError, IOError):
            return None

    def _read_pmbus_hwmon(self, kind, labels, scale):
        """Read a PMBus hwmon value by matching '{kind}*_label' against *labels*.

        Args:
            kind:   hwmon attribute prefix ('in', 'curr', 'power', 'temp').
            labels: iterable of acceptable label strings (lowercase). If empty,
                    the first '{kind}1_input' is used (for unlabelled attrs).
            scale:  divisor to convert the raw sysfs value to base SI units
                    (mV/mA -> 1000, uW -> 1e6, m°C -> 1000).
        Returns:
            float value, or None if the hwmon/attribute is unavailable.
        """
        if not self._pmbus_i2c_dir:
            return None
        hwmon_dirs = glob.glob(os.path.join(self._pmbus_i2c_dir, 'hwmon', 'hwmon*'))
        if not hwmon_dirs:
            return None
        hwmon = hwmon_dirs[0]

        def _read_input(input_path):
            try:
                with open(input_path) as f:
                    return int(f.read().strip()) / scale
            except (OSError, ValueError):
                return None

        if labels:
            for lbl_path in glob.glob(os.path.join(hwmon, '{}*_label'.format(kind))):
                try:
                    with open(lbl_path) as f:
                        lbl = f.read().strip().lower()
                except OSError:
                    continue
                if lbl in labels:
                    return _read_input(lbl_path[:-len('_label')] + '_input')
            return None
        # Unlabelled attribute: use the first index.
        return _read_input(os.path.join(hwmon, '{}1_input'.format(kind)))

    # ------------------------------------------------------------------ #
    #  Presence helper: gpiochip line named in pddf-device.json
    # ------------------------------------------------------------------ #
    def _read_presence_gpio(self):
        """Presence from the configured gpiochip line, or None if unavailable."""
        if not self._presence_gpio_label:
            return None

        if self._presence_gpio_pin is None:
            # Resolved lazily: pmon can start before platform-init exports the
            # gpiochip, so a miss at __init__ time must not be permanent.
            self._presence_gpio_pin = resolve_gpio_pin(
                self._presence_gpio_label, self._presence_gpio_offset)
            if self._presence_gpio_pin is None:
                return None

        return read_gpio_bool(self._presence_gpio_pin,
                              self._presence_gpio_active)

    def get_presence(self):
        return self._impl.get_presence()


    # ------------------------------------------------------------------ #
    #  Model: EEPROM @ 0x4F (20 bytes), fallback to PDDF PMBus
    # ------------------------------------------------------------------ #
    def get_model(self):
        return self._impl.get_model()


    # ------------------------------------------------------------------ #
    #  V/I/P: PMBus hwmon (opt-in via pmbus_hwmon in pddf-device.json)
    # ------------------------------------------------------------------ #
    def get_voltage(self):
        return self._impl.get_voltage()

    def get_current(self):
        return self._impl.get_current()

    def get_power(self):
        return self._impl.get_power()

    def get_input_voltage(self):
        return self._impl.get_input_voltage()

    def get_input_current(self):
        return self._impl.get_input_current()

    def get_input_power(self):
        return self._impl.get_input_power()

    def get_powergood_status(self):
        return self._impl.get_powergood_status()

    def get_serial(self):
        return self._impl.get_serial()

    def get_revision(self):
        return self._impl.get_revision()

    def is_replaceable(self):
        return self._impl.is_replaceable()

    def get_voltage_high_threshold(self):
        return self._impl.get_voltage_high_threshold()

    def get_voltage_low_threshold(self):
        return self._impl.get_voltage_low_threshold()
