#!/usr/bin/env python3
#
# platform.py — PDDF Platform wrapper
#
# Copyright (c) 2024, Juniper Networks, Inc.
# All rights reserved.
#

try:
    from sonic_platform_pddf_base.pddf_platform import PddfPlatform
except ImportError as e:
    raise ImportError("%s - required module not found" % e)


class Platform(PddfPlatform):
    """Juniper PDDF Platform"""

    def __init__(self):
        PddfPlatform.__init__(self)
