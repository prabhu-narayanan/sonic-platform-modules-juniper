#!/usr/bin/env python3
#
# QFX5241-64 (Garnet) Platform Initialization Script
#
# Copyright (C) 2026 Juniper Networks
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
#
# Pre-PDDF initialization for QFX5241-64 (Garnet) platform.
#
# Responsibilities:
#   - Set EFI BootNext so warm/cold reboot returns to SONiC
#   - Copy ONIE EEPROM cache for platform EEPROM plugin
#
# NOT done here (handled by pddf_util.py install via pddf-device.json):
#   - Driver loading  -> custom_kos / std_kos / pddf_kos in pddf-device.json
#   - I2C bus fixup   -> drivers assign static bus numbers; no runtime patch needed
#   - Device instantiation -> pddf_util.py
#
# I2C bus number scheme (static, guaranteed by kernel drivers):
#   iSMT (PCIe 00:1f.4)        : i2c-0
#   MUX1 @0x78 ch0-7           : 0x10-0x17
#   MUX2 @0x70 ch0-7           : 0x20-0x27
#   MUX3 @0x76 ch0-7           : 0x30-0x37
#   Garnet ocores CPLD1 port 0-31 : 0x40-0x5f
#   Garnet ocores CPLD2 port 32-63: 0x60-0x7f
#   Garnet ocores SFP   port 64-65: 0x80-0x81

import subprocess
from sonic_py_common.logger import Logger

SYSLOG_IDENTIFIER = "qfx5241-platform-init"


def log_info(msg):
    Logger(SYSLOG_IDENTIFIER).log_info(msg)


def log_warning(msg):
    Logger(SYSLOG_IDENTIFIER).log_warning(msg)


def log_error(msg):
    Logger(SYSLOG_IDENTIFIER).log_error(msg)



def remove_stale_pmon_container():
    """Remove stale pmon container so pmon.sh creates a fresh one on next start.

    After a reboot, an old pmon container may persist with stale device mounts
    (e.g. /dev/nvme1n1pN) that no longer exist, causing 'docker start' to fail.
    Removing it here (before pmon.service starts) forces pmon.sh to recreate it.
    """
    result = subprocess.run(['docker', 'rm', '-f', 'pmon'],
                            capture_output=True, text=True)
    if result.returncode == 0:
        log_info("Removed stale pmon container")


def setup():
    remove_stale_pmon_container()


if __name__ == '__main__':
    setup()
