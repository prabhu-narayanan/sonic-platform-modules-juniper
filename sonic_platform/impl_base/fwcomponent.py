#!/usr/bin/env python3
#
# impl_base/fwcomponent.py — default FwComponent platform implementation.
#
# Copyright (c) 2026, Juniper Networks, Inc.
# All rights reserved.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# FwComponentImplBase wraps a FwCompInv inventory object (self._fw) and owns
# the component behavior. self._host is the owning FwComponent (ComponentBase),
# used for public re-entry.


class FwComponentImplBase:
    """Default implementation wrapping a FwCompInv inventory object."""

    def __init__(self, host):
        self._host = host

    def get_firmware_version(self):
        return self._host._fw.get_version()

    def install_firmware(self, image_path):
        return self._host._fw.install_firmware(image_path)

    def get_name(self):
        return self._host._fw.get_name()

    def get_description(self):
        return self._host._fw.get_description()

    def update_firmware(self, image_path):
        return self._host.install_firmware(image_path)

    def get_available_firmware_version(self, image_path):
        return self._host.get_firmware_version()

    def get_presence(self):
        if (self._host._fw.index == 0 or self._host._fw.index == 5):
            return True
        if (self._host.get_firmware_version() != "Not Available"):
            return True
        return True

    def get_status(self):
        if (self._host.get_presence()):
            return True
        return False

    def auto_update_firmware(self, image_path, boot_type):
        return 1

    def get_model(self):
        return 'NA'

    def get_serial(self):
        return 'NA'

    def get_revision(self):
        return str(0)

    def get_position_in_parent(self):
        return self._host._fw.index

    def is_replaceable(self):
        return False
