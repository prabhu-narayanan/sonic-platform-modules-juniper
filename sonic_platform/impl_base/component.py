#!/usr/bin/env python3
#
# impl_base/component.py — default Component platform implementation.
#
# Copyright (c) 2026, Juniper Networks, Inc.
# All rights reserved.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# ComponentImplBase holds the Juniper-specific Component API overrides. The
# facade (sonic_platform/component.py, a PddfComponent) owns state and the
# _get_ssd_model mechanic; base-class behavior and state are reached via
# self._host.

try:
    from sonic_platform_pddf_base.pddf_component import PddfComponent
except ImportError as e:
    raise ImportError(str(e) + " - required module not found")


class ComponentImplBase:
    """Default per-platform Component implementation."""

    # Variant-aware SSD "available" (target) firmware version. The QFX5K ships
    # different SSD variants whose firmware version strings and upgrade images
    # differ per model, so a single static "version" cannot describe them.
    # smartctl "Device Model" id -> target ("available") firmware version.
    SSD_VARIANT_TARGET = {
        "SFSA050GM3AA2TO-C-LB-24A-JUN": "SBR12050",
        "SFSA050GM2AK1TO-C-8C-12":      "SBR12005",
    }

    # SSD component name -> block device node (matches pddf-device.json).
    SSD_DEVICE = {
        "SSD-PRIMARY":   "/dev/sda",
        "SSD-SECONDARY": "/dev/sdb",
    }

    def __init__(self, host):
        self._host = host

    def get_available_firmware_version(self, image_path):
        """Retrieves the available (target) firmware version.

        A component whose target depends on the fitted hardware declares an
        "available_version" command in pddf-device.json.  For QFX5K SSDs the
        target is variant-specific and resolved from the installed SSD model.
        Every other component keeps a static "version" in
        platform_components.json.
        """
        component = self._host
        available_cmd = component._get_cmd("available_version")
        if available_cmd is not None:
            result = component.pddf_obj.get_cmd_output(available_cmd)
            if result.returncode != 0:
                return "Unknown"
            return result.stdout.decode("utf-8").strip()

        device = self.SSD_DEVICE.get(component.get_name())
        if device is None:
            return PddfComponent.get_available_firmware_version(component, image_path)

        model = self._host._get_ssd_model(device)
        if model:
            for variant_id, target in self.SSD_VARIANT_TARGET.items():
                if variant_id in model:
                    return target

        # Unknown variant: report current version -> fwutil shows "up-to-date".
        return component.get_firmware_version()

    def get_firmware_update_notification(self, image_path):
        """Return the post-flash action notification message.

        Fixes PddfComponent.get_firmware_update_notification(), which builds
        the message but never returns it.
        """
        component = self._host
        comp_type = component._get_attr("type")
        if comp_type is None:
            return None
        comp_type = comp_type.upper()

        post_flash_reboot = component._get_attr("post_flash_reboot")
        if post_flash_reboot is None or post_flash_reboot == "none":
            return None  # No action required after flash

        if post_flash_reboot == "cold":
            action_msg = " and power reboot device to take effect"
        elif post_flash_reboot == "warm":
            action_msg = " and reboot device to take effect"
        elif post_flash_reboot == "fast":
            action_msg = " and fast reboot device to take effect"
        else:
            raise RuntimeError("Invalid post_flash_reboot value: {}".format(post_flash_reboot))

        return "{} will be updated, please wait for completion{}!".format(comp_type, action_msg)
