#!/usr/bin/env python3
#
# Name: reboot_cause.py, version: 1.0
#
# Description: Blantons (QFX5252) reboot cause detection via CB_FPGA
#              RST_CAUSE_REG register.
#
# The CB_FPGA records reboot cause information in the RST_CAUSE_REG
# register. This is a sticky register that does not get reset under
# global reset conditions (FPGA spec v0.2, Table 95). Bits are W1C
# (write-1-to-clear).
#
# RST_CAUSE_REG bit definitions:
#   Bit 0   : PWR_ON_RST       - Power-on reset (default 1 at POR)
#   Bit 1   : SW_THERM_RST     - SW-initiated thermal suicide (THERMAL_SUICIDE)
#   Bit 2   : WDG_RST          - CB_FPGA watchdog timer expired
#   Bit 3   : HW_THERM_RST     - HW thermal suicide caused by CB (THERMTRIP)
#   Bit 4   : SWB_0_THERM_RST  - HW thermal suicide caused by SWB_0
#   Bit 5   : SWB_1_THERM_RST  - HW thermal suicide caused by SWB_1
#   Bit 8   : CLD_RST          - System PSCOLD de-asserted from good state (cold reset)
#   Bits 31:16 : SW_RST_COOKIES - RW field for SW to read/write reboot context
#
# Boot-time readout sequence:
#   1. Platform driver reads RST_CAUSE_REG immediately after CPU is available
#   2. Bit fields are decoded and mapped to SONiC reboot cause constants
#   3. Bits are cleared by writing 1 to each set bit (W1C)
#   4. Cause is stored persistently
#
# Copyright (c) 2024, Juniper Networks, Inc.
# All rights reserved.
#

import os
import mmap
import struct
import syslog

SYSLOG_IDENTIFIER = "Juniper-RebootCause"

# CB_FPGA PCI BDF for Blantons — auto-detect by PCI vendor:device ID
# QFX5252: 0000:03:00.0, CX8325H: 0000:02:00.0
# Vendor 0x1590 (HPE), Device 0x0180 (FPGA F0)
CB_FPGA_PCI_BDF = None
CB_FPGA_RESOURCE0 = None

def _find_cb_fpga_bdf():
    """Find the CB_FPGA PCI BDF by scanning for vendor:device 1590:0180."""
    global CB_FPGA_PCI_BDF, CB_FPGA_RESOURCE0
    if CB_FPGA_RESOURCE0 is not None:
        _log_debug("CB_FPGA already cached: BDF={} resource={}".format(
            CB_FPGA_PCI_BDF, CB_FPGA_RESOURCE0))
        return CB_FPGA_RESOURCE0

    _log_info("Scanning PCI bus for CB_FPGA (vendor=0x1590 device=0x0180)")
    pci_base = "/sys/bus/pci/devices"

    if not os.path.isdir(pci_base):
        _log_error("PCI sysfs not available: {} does not exist".format(pci_base))
        return None

    # Known BDFs to check first (fast path)
    for bdf in ["0000:02:00.0", "0000:03:00.0"]:
        _log_debug("Fast-path checking BDF: {}".format(bdf))
        try:
            vendor_path = os.path.join(pci_base, bdf, "vendor")
            device_path = os.path.join(pci_base, bdf, "device")
            with open(vendor_path) as f:
                vendor = f.read().strip()
            with open(device_path) as f:
                device = f.read().strip()
            _log_debug("BDF {} -> vendor={} device={}".format(bdf, vendor, device))
            if vendor == "0x1590" and device == "0x0180":
                CB_FPGA_PCI_BDF = bdf
                CB_FPGA_RESOURCE0 = os.path.join(pci_base, bdf, "resource0")
                _log_info("CB_FPGA found at BDF={} resource={}".format(bdf, CB_FPGA_RESOURCE0))
                if not os.path.exists(CB_FPGA_RESOURCE0):
                    _log_error("WARNING: resource0 file does not exist: {}".format(CB_FPGA_RESOURCE0))
                return CB_FPGA_RESOURCE0
        except (OSError, IOError) as e:
            _log_debug("Fast-path BDF {} not accessible: {}".format(bdf, e))
            continue

    # Fallback: scan all PCI devices
    _log_info("Fast-path BDFs not found, scanning all PCI devices")
    try:
        entries = sorted(os.listdir(pci_base))
        _log_debug("PCI devices found: {} entries".format(len(entries)))
        for entry in entries:
            try:
                vendor_path = os.path.join(pci_base, entry, "vendor")
                device_path = os.path.join(pci_base, entry, "device")
                with open(vendor_path) as f:
                    vendor = f.read().strip()
                with open(device_path) as f:
                    device = f.read().strip()
                if vendor == "0x1590":
                    _log_debug("HPE device at {}: vendor={} device={}".format(
                        entry, vendor, device))
                if vendor == "0x1590" and device == "0x0180":
                    CB_FPGA_PCI_BDF = entry
                    CB_FPGA_RESOURCE0 = os.path.join(pci_base, entry, "resource0")
                    _log_info("CB_FPGA found at BDF={} (full scan)".format(entry))
                    if not os.path.exists(CB_FPGA_RESOURCE0):
                        _log_error("WARNING: resource0 file does not exist: {}".format(CB_FPGA_RESOURCE0))
                    return CB_FPGA_RESOURCE0
            except (OSError, IOError) as e:
                _log_debug("Cannot read PCI device {}: {}".format(entry, e))
                continue
    except OSError as e:
        _log_error("Cannot list PCI devices at {}: {}".format(pci_base, e))

    _log_error("CB_FPGA NOT FOUND on PCI bus after scanning all devices")
    return None

# RST_CAUSE_REG offset within CB_FPGA BAR0
# From FPGA spec v0.2, Table 95
RST_CAUSE_REG_OFFSET = 0x20

# RST_CAUSE_REG bit masks
RST_CAUSE_PWR_ON_RST       = (1 << 0)   # Bit 0: Power-on reset
RST_CAUSE_SW_THERM_RST     = (1 << 1)   # Bit 1: SW thermal suicide
RST_CAUSE_WDG_RST          = (1 << 2)   # Bit 2: Watchdog timer expired
RST_CAUSE_HW_THERM_RST     = (1 << 3)   # Bit 3: HW thermal suicide (CB)
RST_CAUSE_SWB_0_THERM_RST  = (1 << 4)   # Bit 4: SWB_0 thermal suicide
RST_CAUSE_SWB_1_THERM_RST  = (1 << 5)   # Bit 5: SWB_1 thermal suicide
RST_CAUSE_CLD_RST          = (1 << 8)   # Bit 8: Cold reset (PSCOLD)
RST_CAUSE_SW_RST_COOKIES_MASK = 0xFFFF0000  # Bits 31:16: SW cookies
RST_CAUSE_HW_BITS_MASK     = 0x0000013F     # All HW cause bits (0-5, 8)

# Persistent file to cache the HW reboot cause (read once at boot)
REBOOT_CAUSE_CACHE_FILE = "/tmp/reboot-cause-hw.txt"


def _log_debug(msg):
    syslog.openlog(SYSLOG_IDENTIFIER)
    syslog.syslog(syslog.LOG_DEBUG, msg)
    syslog.closelog()


def _log_info(msg):
    syslog.openlog(SYSLOG_IDENTIFIER)
    syslog.syslog(syslog.LOG_INFO, msg)
    syslog.closelog()


def _log_error(msg):
    syslog.openlog(SYSLOG_IDENTIFIER)
    syslog.syslog(syslog.LOG_ERR, msg)
    syslog.closelog()


def _read_rst_cause_reg():
    """Read the 32-bit RST_CAUSE_REG from CB_FPGA BAR0 via mmap.

    Returns:
        int: Register value, or None on failure.
    """
    resource_path = _find_cb_fpga_bdf()
    if resource_path is None:
        _log_error("CB_FPGA not found on PCI bus")
        return None
    offset = RST_CAUSE_REG_OFFSET

    _log_info("Reading RST_CAUSE_REG: resource={} offset=0x{:X}".format(
        resource_path, offset))
    fd = None
    try:
        fd = os.open(resource_path, os.O_RDWR | os.O_SYNC)
        _log_debug("Opened resource0 fd={}".format(fd))
        # mmap requires page-aligned offset
        page_size = mmap.PAGESIZE
        page_offset = offset & ~(page_size - 1)
        page_remainder = offset - page_offset
        _log_debug("mmap: page_size={} page_offset=0x{:X} remainder=0x{:X}".format(
            page_size, page_offset, page_remainder))

        with mmap.mmap(fd, page_size, mmap.MAP_SHARED,
                       mmap.PROT_READ | mmap.PROT_WRITE,
                       offset=page_offset) as mm:
            mm.seek(page_remainder)
            raw = mm.read(4)
            if raw is None or len(raw) < 4:
                _log_error("Short read from mmap: got {} bytes".format(
                    0 if raw is None else len(raw)))
                return None
            value = struct.unpack("<I", raw)[0]
            _log_info("RST_CAUSE_REG raw value: 0x{:08X} (hw_bits=0x{:03X}, cookies=0x{:04X})".format(
                value, value & RST_CAUSE_HW_BITS_MASK,
                (value & RST_CAUSE_SW_RST_COOKIES_MASK) >> 16))
            return value
    except OSError as e:
        _log_error("Failed to read RST_CAUSE_REG: {} (resource={})".format(e, resource_path))
        return None
    except Exception as e:
        _log_error("Unexpected error reading RST_CAUSE_REG: {} ({})".format(e, type(e).__name__))
        return None
    finally:
        if fd is not None:
            os.close(fd)
            _log_debug("Closed resource0 fd={}".format(fd))


def _clear_rst_cause_reg(value):
    """Clear sticky bits in RST_CAUSE_REG by writing 1 to set bits (W1C).

    Only clears hardware cause bits (0-8). SW_RST_COOKIES are left intact.

    Args:
        value: The register value read (bits to clear).
    """
    resource_path = _find_cb_fpga_bdf()
    if resource_path is None:
        _log_error("CB_FPGA not found on PCI bus, cannot clear RST_CAUSE_REG")
        return
    offset = RST_CAUSE_REG_OFFSET
    # Only clear HW bits, preserve cookies
    clear_value = value & RST_CAUSE_HW_BITS_MASK

    if clear_value == 0:
        _log_debug("No HW bits set, nothing to clear")
        return

    _log_info("Clearing RST_CAUSE_REG: W1C value=0x{:08X} (preserving cookies)".format(clear_value))
    fd = None
    try:
        fd = os.open(resource_path, os.O_RDWR | os.O_SYNC)
        page_size = mmap.PAGESIZE
        page_offset = offset & ~(page_size - 1)
        page_remainder = offset - page_offset

        with mmap.mmap(fd, page_size, mmap.MAP_SHARED,
                       mmap.PROT_READ | mmap.PROT_WRITE,
                       offset=page_offset) as mm:
            mm.seek(page_remainder)
            mm.write(struct.pack("<I", clear_value))
            _log_info("RST_CAUSE_REG cleared with: 0x{:08X}".format(clear_value))
            # Verify the clear
            mm.seek(page_remainder)
            verify_raw = mm.read(4)
            verify_val = struct.unpack("<I", verify_raw)[0]
            remaining = verify_val & RST_CAUSE_HW_BITS_MASK
            if remaining:
                _log_error("W1C incomplete: after clear, HW bits still set: 0x{:03X}".format(remaining))
            else:
                _log_debug("W1C verified: HW bits cleared successfully")
    except OSError as e:
        _log_error("Failed to clear RST_CAUSE_REG: {}".format(e))
    except Exception as e:
        _log_error("Unexpected error clearing RST_CAUSE_REG: {} ({})".format(e, type(e).__name__))
    finally:
        if fd is not None:
            os.close(fd)


def read_hw_reboot_cause():
    """Read and decode the hardware reboot cause from CB_FPGA RST_CAUSE_REG.

    Reads the register, decodes the cause, clears sticky bits, and caches
    the result. On subsequent calls, returns the cached result.

    Returns:
        tuple: (REBOOT_CAUSE_TYPE, description_string)
            REBOOT_CAUSE_TYPE is a string constant from sonic_platform_base.
    """
    # Import here to avoid circular imports
    from sonic_platform_base.chassis_base import ChassisBase

    _log_info("read_hw_reboot_cause() called")

    # Check cache first (register should only be read once at boot)
    if os.path.exists(REBOOT_CAUSE_CACHE_FILE):
        _log_debug("Cache file exists: {}".format(REBOOT_CAUSE_CACHE_FILE))
        try:
            with open(REBOOT_CAUSE_CACHE_FILE, 'r') as f:
                raw_cache = f.read().strip()
            _log_debug("Cache file content: '{}'".format(raw_cache))
            cached = raw_cache.split('|', 1)
            if len(cached) == 2:
                cause_type = int(cached[0])
                description = cached[1] if cached[1] != 'None' else None
                _log_info("Returning cached reboot cause: type={}, desc={}".format(
                    cause_type, description))
                return (cause_type, description)
            else:
                _log_error("Cache file malformed (no '|' separator): '{}'".format(raw_cache))
        except Exception as e:
            _log_info("Cache read failed, will read register: {} ({})".format(e, type(e).__name__))
    else:
        _log_info("No cache file at {}, reading register fresh".format(REBOOT_CAUSE_CACHE_FILE))

    # Read the register
    reg_value = _read_rst_cause_reg()
    if reg_value is None:
        _log_error("Cannot read RST_CAUSE_REG, returning NON_HARDWARE")
        return (ChassisBase.REBOOT_CAUSE_NON_HARDWARE, None)

    # Decode the cause - check bits in priority order
    hw_bits = reg_value & RST_CAUSE_HW_BITS_MASK
    sw_cookies = (reg_value & RST_CAUSE_SW_RST_COOKIES_MASK) >> 16

    _log_info("Decoding: reg=0x{:08X} hw_bits=0x{:03X} sw_cookies=0x{:04X}".format(
        reg_value, hw_bits, sw_cookies))
    _log_debug("Individual bits: PWR_ON={} SW_THERM={} WDG={} HW_THERM={} "
              "SWB0_THERM={} SWB1_THERM={} CLD={}".format(
                  bool(hw_bits & RST_CAUSE_PWR_ON_RST),
                  bool(hw_bits & RST_CAUSE_SW_THERM_RST),
                  bool(hw_bits & RST_CAUSE_WDG_RST),
                  bool(hw_bits & RST_CAUSE_HW_THERM_RST),
                  bool(hw_bits & RST_CAUSE_SWB_0_THERM_RST),
                  bool(hw_bits & RST_CAUSE_SWB_1_THERM_RST),
                  bool(hw_bits & RST_CAUSE_CLD_RST)))

    cause_type = ChassisBase.REBOOT_CAUSE_NON_HARDWARE
    description = None

    if hw_bits == 0 and sw_cookies != 0:
        # SW reboot - decode from cookies
        cause_type = ChassisBase.REBOOT_CAUSE_NON_HARDWARE
        description = "Software reboot (cookies: 0x{:04X})".format(sw_cookies)
    elif hw_bits == 0 and sw_cookies == 0:
        # No cause set - unknown/default
        cause_type = ChassisBase.REBOOT_CAUSE_NON_HARDWARE
        description = None
    elif hw_bits & RST_CAUSE_PWR_ON_RST:
        cause_type = ChassisBase.REBOOT_CAUSE_POWER_LOSS
        description = "Power-on reset"
    elif hw_bits & RST_CAUSE_SW_THERM_RST:
        cause_type = ChassisBase.REBOOT_CAUSE_THERMAL_OVERLOAD_OTHER
        description = "SW-initiated thermal shutdown"
    elif hw_bits & RST_CAUSE_WDG_RST:
        cause_type = ChassisBase.REBOOT_CAUSE_WATCHDOG
        description = "CB_FPGA watchdog expired"
    elif hw_bits & RST_CAUSE_HW_THERM_RST:
        cause_type = ChassisBase.REBOOT_CAUSE_THERMAL_OVERLOAD_CPU
        description = "HW thermal suicide (THERMTRIP, CB)"
    elif hw_bits & RST_CAUSE_SWB_0_THERM_RST:
        cause_type = ChassisBase.REBOOT_CAUSE_THERMAL_OVERLOAD_ASIC
        description = "SWB_0 thermal suicide"
    elif hw_bits & RST_CAUSE_SWB_1_THERM_RST:
        cause_type = ChassisBase.REBOOT_CAUSE_THERMAL_OVERLOAD_ASIC
        description = "SWB_1 thermal suicide"
    elif hw_bits & RST_CAUSE_CLD_RST:
        cause_type = ChassisBase.REBOOT_CAUSE_POWER_LOSS
        description = "System cold reset (PSCOLD)"
    else:
        cause_type = ChassisBase.REBOOT_CAUSE_HARDWARE_OTHER
        description = "Unknown HW cause (reg: 0x{:08X})".format(reg_value)

    _log_info("Decoded reboot cause: type={}, desc={}".format(cause_type, description))

    # Clear sticky bits after reading
    _clear_rst_cause_reg(reg_value)

    # Cache the result
    try:
        with open(REBOOT_CAUSE_CACHE_FILE, 'w') as f:
            f.write("{}|{}".format(cause_type, description))
    except Exception as e:
        _log_error("Failed to cache reboot cause: {}".format(e))

    return (cause_type, description)
