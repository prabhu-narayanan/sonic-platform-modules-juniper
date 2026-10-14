#!/usr/bin/env python3
#
# QFX5241-64 (Garnet) PDDF pre-device-create hook
#
# Copyright (C) 2026 Juniper Networks
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
#
# Invoked by pddf_pre_device_create.sh, which pddf_util.py runs after the
# kernel modules are loaded and before create_pddf_devices() walks
# pddf-device.json.
#
# The CPU SMBus (i2c-0) is the parent of the PCA9548 muxes. The I2C core
# refuses a client on a mux channel when a client on a parent bus already uses
# the address, and returns -EBUSY (-16). i2c_i801 registers SPD clients on
# i2c-0 at boot and ee1004 then claims the 0x36/0x37 page-select addresses,
# which collides with VRM5 (0x36 on MUX1 channel 5). Unbinding ee1004 makes it
# release those two addresses.
#
# The SPD client itself cannot be removed from user space and keeps its own
# address (the PSU EEPROMs therefore are not instantiated through PDDF).

import os
import re

from sonic_py_common.logger import Logger

SYSLOG_IDENTIFIER = "qfx5241-pre-device-create"
EE1004_DRIVER_DIR = "/sys/bus/i2c/drivers/ee1004"
CPU_SMBUS_CLIENT = re.compile(r"^0-[0-9a-f]{4}$")


def log_info(msg):
    Logger(SYSLOG_IDENTIFIER).log_info(msg)


def log_warning(msg):
    Logger(SYSLOG_IDENTIFIER).log_warning(msg)


def unbind_ee1004_from_cpu_smbus(driver_dir=EE1004_DRIVER_DIR):
    """Unbind ee1004 from its clients on i2c-0; return the clients unbound."""
    try:
        entries = sorted(os.listdir(driver_dir))
    except OSError:
        return []                       # ee1004 not loaded: nothing holds 0x36

    unbound = []
    for name in entries:
        if not CPU_SMBUS_CLIENT.match(name):
            continue
        try:
            with open(os.path.join(driver_dir, "unbind"), "w") as f:
                f.write(name)
        except OSError as e:
            log_warning("Could not unbind ee1004 from {}: {}".format(name, e))
            continue
        unbound.append(name)
        log_info("Unbound ee1004 from {} to free the 0x36/0x37 addresses".format(name))
    return unbound


def main():
    unbind_ee1004_from_cpu_smbus()


if __name__ == '__main__':
    main()
