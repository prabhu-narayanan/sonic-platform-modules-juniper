#!/usr/bin/env python3
#
# Name: component.py, version: 1.0
#
# Description: Platform Component class for Juniper PTX10002.
#
# Subclasses PddfComponent to inherit firmware version/update/auto-update
# behaviour driven entirely by COMPONENT entries in pddf-device.json.
#
# Fixes PddfComponent.get_firmware_update_notification() which builds the
# notification message but forgets to return it.
#
# Copyright (c) 2024, Juniper Networks, Inc.
# All rights reserved.
#

try:
    from sonic_platform_pddf_base.pddf_component import PddfComponent
except ImportError as e:
    raise ImportError(str(e) + " - required module not found")


class Component(PddfComponent):
    """Platform Component — thin wrapper over PddfComponent."""

    def __init__(self, component_index, pddf_data=None, pddf_plugin_data=None):
        PddfComponent.__init__(self, component_index, pddf_data, pddf_plugin_data)
        from sonic_platform.override import load_impl
        self._impl = load_impl("Component", self)

    def _get_ssd_model(self, device):
        """Return the SSD model id (smartctl "Device Model"), or None."""
        cmd = "smartctl -a {} | awk -F: '/Device Model/{{print $2}}'".format(device)
        result = self.pddf_obj.get_cmd_output(cmd)
        if result.returncode != 0:
            return None
        return result.stdout.decode("utf-8").strip()

    def get_available_firmware_version(self, image_path):
        return self._impl.get_available_firmware_version(image_path)

    def get_firmware_update_notification(self, image_path):
        return self._impl.get_firmware_update_notification(image_path)

