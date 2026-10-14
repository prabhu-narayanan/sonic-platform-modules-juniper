#!/usr/bin/env python3
#
# impl_base/chassis.py — default Chassis platform implementation.
#
# Copyright (c) 2026, Juniper Networks, Inc.
# All rights reserved.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# ChassisImplBase holds ONLY the inherited (ChassisBase/PddfChassis) public API
# for the Chassis. The facade (sonic_platform/chassis.py) owns construction,
# state, and the generic mechanics (_devmem_read/_devmem_clear, the SFP worker,
# ASIC-thermal sync, PORT_TABLE init); these methods read them via self._host.
# Platforms override only the inherited methods that differ.
# differs.

import time
import syslog
import queue

try:
    from sonic_platform_base.chassis_base import ChassisBase
except ImportError as e:
    raise ImportError(str(e) + " - required module not found")

SYSLOG_IDENTIFIER = "Juniper-Chassis"

# QFX5241 reboot-cause BIOS NVRAM register addresses
_RCAUSE_SOFT    = '0xFC80020A'  # soft/warm/fast-reboot, RTC, WDT
_RCAUSE_HW      = '0xFC800208'  # CPU CATERR/MSMI, swizzle, button, power, SW, FPGA
_RCAUSE_THERMAL = '0xFC800207'  # thermal overload, power loss, SW halt


def log_info(msg):
    syslog.openlog(SYSLOG_IDENTIFIER)
    syslog.syslog(syslog.LOG_INFO, msg)
    syslog.closelog()


class ChassisImplBase:
    """Default per-platform Chassis implementation.

    Contract:
      * This class holds ONLY the inherited (ChassisBase/PddfChassis) public API
        that a platform may override — get_all_thermals, get_num_thermals,
        get_revision, get_change_event, get_reboot_cause, get_thermal_manager,
        set_status_led, get_status_led.
      * self._host is the owning Chassis facade (a PddfChassis). The facade owns
        construction, ALL internal mechanics/helpers (_sync_asic_thermal,
        _asic_sensors_enabled, _sfp_event_worker, _init_port_table_db,
        _init_sfp_thermals, _devmem_read, _devmem_clear), and the state; these
        methods reach them via self._host.
      * Platforms subclass this in <platform>/platform_impl/chassis.py and
        override only the inherited methods that differ (e.g. get_reboot_cause).
    """

    def __init__(self, host):
        self._host = host

    # ------------------------------------------------------------------ #
    #  Thermal enumeration (inherited API)
    # ------------------------------------------------------------------ #
    def get_all_thermals(self):
        self._host._sync_asic_thermal()
        return self._host._thermal_list

    def get_num_thermals(self):
        self._host._sync_asic_thermal()
        return len(self._host._thermal_list)

    def get_revision(self):
        """Return chassis hardware revision from system EEPROM.

        The PTX10002 EEPROM stores the hardware revision in the
        'Label Revision' field (TLV code 0x27), NOT 'Device Version'
        (0x26).  The PDDF base reads 0x26, which doesn't exist, so
        override to read 0x27 instead.
        """
        return self._host._sys_eeprom.label_revision_str()

    # ------------------------------------------------------------------ #
    #  SFP change-event polling (inherited API)
    # ------------------------------------------------------------------ #
    def get_change_event(self, timeout):
        """Detect SFP presence changes and queue events for worker thread."""
        chassis = self._host
        start_ms = time.time() * 1000
        port_dict = {}
        change_dict = {'sfp': port_dict}

        while True:
            time.sleep(0.5)

            while True:
                try:
                    port_num, success = chassis._sfp_init_complete_queue.get_nowait()
                    chassis._sfp_pending_init.discard(port_num)
                    if success:
                        if not chassis._report_presence_immediately:
                            chassis.xcvr_presence_map[port_num] = '1'
                            port_dict[port_num] = '1'
                            log_info("Port {}: Init complete, reporting presence to xcvrd".format(port_num))
                    else:
                        log_info("Port {}: Init failed, not reporting presence".format(port_num))
                except queue.Empty:
                    break

            for port_num, sfp in chassis._sfp_poll_list:
                try:
                    is_present = sfp.get_presence()
                    if is_present and chassis.xcvr_presence_map[port_num] == '0':
                        if chassis._report_presence_immediately:
                            chassis.xcvr_presence_map[port_num] = '1'
                            port_dict[port_num] = '1'
                        # Module present but not yet tracked by this process.
                        if sfp.is_initialized():
                            # Already initialized by a previous instance (e.g.
                            # across `config reload`): the optoe driver and the
                            # module's power/reset state persist. Report presence
                            # directly WITHOUT re-running the destructive reset
                            # cycle, which would tear down a live link that syncd
                            # has already re-established.
                            chassis.xcvr_presence_map[port_num] = '1'
                            port_dict[port_num] = '1'
                            chassis._sfp_pending_init.discard(port_num)
                            log_info("Port {}: Already initialized, reporting presence without re-init".format(port_num))
                        elif port_num not in chassis._sfp_pending_init:
                            # Cold boot / fresh insertion - queue full init.
                            chassis._sfp_pending_init.add(port_num)
                            chassis._sfp_event_queue.put((port_num, 'insert'))
                            log_info("Port {}: Insert detected, queued for init".format(port_num))
                    elif not is_present and chassis.xcvr_presence_map[port_num] == '1':
                        chassis.xcvr_presence_map[port_num] = '0'
                        port_dict[port_num] = '0'
                        chassis._sfp_pending_init.discard(port_num)
                        chassis._sfp_event_queue.put((port_num, 'remove'))
                        log_info("Port {}: Remove detected, queued for cleanup".format(port_num))
                    elif not is_present and port_num in chassis._sfp_pending_init:
                        chassis._sfp_pending_init.discard(port_num)
                        chassis._sfp_event_queue.put((port_num, 'remove'))
                        log_info("Port {}: Removed during init, queued for cleanup".format(port_num))
                except Exception as e:
                    log_info("Port {} get_presence() exception: {}".format(port_num, e))
                    continue

            if len(port_dict) > 0:
                return True, change_dict

            now_ms = time.time() * 1000
            if timeout is not None and (now_ms - start_ms >= timeout):
                return True, change_dict

    # ------------------------------------------------------------------ #
    #  Reboot cause (inherited API; platform-divergent decode)
    #  Mechanics (_devmem_read/_devmem_clear) live on the facade.
    # ------------------------------------------------------------------ #
    def get_reboot_cause(self):
        """Return the cause of the previous reboot.

        Reads three sticky-bit registers in the QFX5241 BIOS NVRAM.
        """
        val = self._host._devmem_read(_RCAUSE_SOFT)
        if val and val != '0x00':
            self._host._devmem_clear(_RCAUSE_SOFT)
            if val == '0x01':
                return (ChassisBase.REBOOT_CAUSE_HARDWARE_OTHER, 'RTC Battery Error')
            elif val == '0x02':
                return (ChassisBase.REBOOT_CAUSE_WATCHDOG, None)
            elif val == '0x04':
                return (ChassisBase.REBOOT_CAUSE_NON_HARDWARE, 'warm-reboot')
            elif val == '0x08':
                return (ChassisBase.REBOOT_CAUSE_NON_HARDWARE, 'fast-reboot')
            elif val == '0x10':
                return (ChassisBase.REBOOT_CAUSE_NON_HARDWARE, 'soft-reboot')

        val = self._host._devmem_read(_RCAUSE_HW)
        if val and val != '0x00':
            self._host._devmem_clear(_RCAUSE_HW)
            if val == '0x01':
                return (ChassisBase.REBOOT_CAUSE_HARDWARE_OTHER, 'FPGA Reset')
            elif val == '0x04':
                return (ChassisBase.REBOOT_CAUSE_HARDWARE_OTHER, 'CPU Caterr')
            elif val == '0x08':
                return (ChassisBase.REBOOT_CAUSE_HARDWARE_OTHER, 'CPU Msmi')
            elif val == '0x10':
                return (ChassisBase.REBOOT_CAUSE_HARDWARE_OTHER, 'Swizzle Reset')
            elif val == '0x20':
                return (ChassisBase.REBOOT_CAUSE_HARDWARE_OTHER, 'Reset Button')
            elif val in ('0x02', '0x40'):
                return (ChassisBase.REBOOT_CAUSE_POWER_LOSS, None)
            elif val == '0x80':
                return (ChassisBase.REBOOT_CAUSE_NON_HARDWARE, None)

        val = self._host._devmem_read(_RCAUSE_THERMAL)
        if val and val != '0x00':
            self._host._devmem_clear(_RCAUSE_THERMAL)
            if val == '0x01':
                return (ChassisBase.REBOOT_CAUSE_HARDWARE_OTHER, 'Software Halt')
            elif val == '0x02':
                return (ChassisBase.REBOOT_CAUSE_POWER_LOSS, None)
            elif val == '0x04':
                return (ChassisBase.REBOOT_CAUSE_THERMAL_OVERLOAD_OTHER, None)

        return (ChassisBase.REBOOT_CAUSE_HARDWARE_OTHER, 'Unknown reason')

    # ------------------------------------------------------------------ #
    #  Thermal manager
    # ------------------------------------------------------------------ #
    def get_thermal_manager(self):
        """Return the ThermalManager class for thermalctld."""
        chassis = self._host
        if chassis.get_num_fans() == 0:
            log_info("get_thermal_manager: no system fans (liquid-cooled SKU) - "
                     "using shutdown-only thermal policy")
        from sonic_platform.thermal_manager import ThermalManager
        return ThermalManager

    def initizalize_system_led(self):
        """No-op system-LED init (kept for CLI compatibility)."""
        return True

    # ------------------------------------------------------------------ #
    #  System LED (front-panel SYS_LED via PDDF framework)
    # ------------------------------------------------------------------ #
    def set_status_led(self, color):
        """Set the front-panel system LED colour via PDDF framework (SYS_LED)."""
        chassis = self._host
        if color in (None, "", "no_change"):
            return True
        ok = chassis.set_system_led(chassis.SYS_LED_NAME, color)
        if not ok:
            log_info("set_status_led: failed to set '{}'".format(color))
        return ok

    def get_status_led(self):
        """Return the current front-panel system LED colour name."""
        chassis = self._host
        return chassis.get_system_led(chassis.SYS_LED_NAME)
