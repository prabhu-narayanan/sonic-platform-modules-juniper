#!/usr/bin/env python3
#
# sfp_qfx5241.py — QFX5241-specific SFP GPIO helper functions
#
# Copyright (c) 2026, Juniper Networks, Inc.
# All rights reserved.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# The QFX5241 uses a dual-CPLD GPIO layout for 64 QSFP-DD ports split
# across two CPLDs, plus 2 SFP ports:
#
#   cpld0_port_range  — JSON key for CPLD0 port range (e.g., "1-32")
#   cpld1_port_range  — JSON key for CPLD1 port range (e.g., "33-64")
#   gpio_port_map     — 66-element list in SFP_CTRL.i2c.dev_attr mapping
#                       0-based port index → CPLD-relative GPIO offset
#
# These helpers are imported by sfp.py via feature-detection:
#   if is_qfx5241_gpio_schema(sfp_ctrl_attr): ...
#
# To add GPIO support for a new platform, create a new sfp_<platform>.py
# with its own schema-detect + offset/label resolver functions.


def is_qfx5241_gpio_schema(sfp_ctrl_attr):
    """Return True if sfp_ctrl_attr describes QFX5241's dual-CPLD GPIO layout.

    Detects QFX5241 by presence of both CPLD range keys and CPLD-split
    GPIO presence labels in the SFP_CTRL JSON entry.
    """
    return bool(
        sfp_ctrl_attr.get("cpld0_port_range") and
        sfp_ctrl_attr.get("cpld1_port_range") and
        sfp_ctrl_attr.get("gpio_presence_label_cpld0") and
        sfp_ctrl_attr.get("gpio_presence_label_cpld1")
    )


def get_qfx5241_gpio_offset(port_index, sfp_ctrl_attr):
    """Map 0-based port_index to a CPLD-relative GPIO offset for QFX5241.

    Args:
        port_index:    0-based port index (0–65)
        sfp_ctrl_attr: SFP_CTRL.i2c.dev_attr dict from pddf-device.json

    Returns:
        int: CPLD-relative GPIO bit offset for this port
    """
    port_num = port_index + 1
    gpio_port_map = sfp_ctrl_attr.get("gpio_port_map", [])
    if port_num <= 64 and gpio_port_map:
        mapped = gpio_port_map[port_index]
        return mapped if port_num <= 32 else mapped - 32
    # SFP ports (65-66) do not use the gpio_port_map
    return port_num - 65


def resolve_qfx5241_gpio_label(port_index, sfp_ctrl_attr, function_name, port_type):
    """Resolve the GPIO label for a QFX5241 port using dual-CPLD schema.

    Args:
        port_index:    0-based port index
        sfp_ctrl_attr: SFP_CTRL.i2c.dev_attr dict from pddf-device.json
        function_name: GPIO function ("presence", "reset", "lpmod", …)
        port_type:     "sfp" or "osfp"

    Returns:
        str: gpiochip label, or None if this function+type has no QFX5241 override
    """
    # SFP TX-disable has its own dedicated label on QFX5241
    if function_name == "txdisable" and port_type == "sfp":
        label = sfp_ctrl_attr.get("gpio_txdis_label_sfp")
        if label:
            return label

    if port_type == "osfp":
        port_num = port_index + 1

        def _in_range(range_str):
            if not range_str:
                return False
            try:
                start, end = map(int, range_str.split("-"))
                return start <= port_num <= end
            except ValueError:
                return False

        if _in_range(sfp_ctrl_attr.get("cpld0_port_range", "")):
            return sfp_ctrl_attr.get("gpio_{}_label_cpld0".format(function_name), "")
        if _in_range(sfp_ctrl_attr.get("cpld1_port_range", "")):
            return sfp_ctrl_attr.get("gpio_{}_label_cpld1".format(function_name), "")

    return None
