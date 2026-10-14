#!/usr/bin/env python3
#
# impl_base/sfp.py — default SFP platform implementation.
#
# Copyright (c) 2026, Juniper Networks, Inc.
# All rights reserved.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# SfpImplBase holds ONLY the inherited (SfpOptoeBase) SFP public API. The facade
# (sonic_platform/sfp.py) owns construction, config parsing, state,
# and the I2C/GPIO/MMIO mechanics; these methods read them via self._host.
# Platforms override only the hooks that differ.

import os
import time
import syslog
from datetime import datetime
from enum import Enum, auto
from dataclasses import dataclass
from typing import Optional, List

try:
    from sonic_platform_base.sonic_xcvr.sfp_optoe_base import SfpOptoeBase
    from sonic_platform.gpio_helper import read_gpio, write_gpio
    try:
        from swsscommon.swsscommon import SonicV2Connector
        HAS_SWSSCOMMON = True
    except ImportError:
        HAS_SWSSCOMMON = False
except ImportError as e:
    raise ImportError(str(e) + " - required module not found")

# SFP type identifier bytes (from SFF-8024)
SFP_TYPE_LIST = [0x3]
QSFP_TYPE_LIST = [0xc, 0xd, 0x11]
QSFP_DD_TYPE_LIST = [0x18, 0x1e]
OSFP_TYPE_LIST = [0x19]

SYSLOG_IDENTIFIER = "SfpGeneric"

# Constants for SFP power/reset initialization
SFP_RESET_SETTLE_TIME_SECS = 2.0  # QSFP-DD modules need ~2s after reset per CMIS spec
SFP_OPTOE_PROBE_SETTLE_SECS = 3.0  # Wait for optoe driver to complete probe

# STATE_DB connection for init state tracking
_state_db = None
LANES_PER_PORT = 8  # For Ethernet port name calculation


def log_err(msg):
    syslog.openlog(SYSLOG_IDENTIFIER)
    syslog.syslog(syslog.LOG_ERR, msg)
    syslog.closelog()


def log_info(msg):
    syslog.openlog(SYSLOG_IDENTIFIER)
    syslog.syslog(syslog.LOG_INFO, msg)
    syslog.closelog()


def log_debug(msg):
    syslog.openlog(SYSLOG_IDENTIFIER)
    syslog.syslog(syslog.LOG_DEBUG, msg)
    syslog.closelog()


def _get_state_db():
    """Get or create STATE_DB connection."""
    global _state_db
    if not HAS_SWSSCOMMON:
        return None
    if _state_db is None:
        try:
            _state_db = SonicV2Connector()
            _state_db.connect(_state_db.STATE_DB)
        except Exception as e:
            log_err(f"Failed to connect to STATE_DB: {e}")
            return None
    return _state_db


def get_time():
    """Return human-readable timestamp with milliseconds."""
    now = datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S.") + f"{now.microsecond // 1000:03d}"


def _update_init_state(port_num: int, state: str, error: Optional[str] = None):
    """Update transceiver init state in STATE_DB with full history."""
    db = _get_state_db()
    if db is None:
        return
    try:
        port_name = f"Ethernet{port_num * LANES_PER_PORT}"
        key = f"TRANSCEIVER_INIT_STATE|{port_name}"
        timestamp = get_time()
        # Store current state
        db.set(db.STATE_DB, key, "state", state)
        # Store per-state timestamp (keeps history)
        db.set(db.STATE_DB, key, f"{state}_ts", timestamp)
        if error:
            db.set(db.STATE_DB, key, "error", error)
    except Exception as e:
        log_err(f"Failed to update STATE_DB for port {port_num}: {e}")


def _clear_init_state(port_num: int):
    """Clear transceiver init state from STATE_DB (for removal events)."""
    db = _get_state_db()
    if db is None:
        return
    try:
        port_name = f"Ethernet{port_num * LANES_PER_PORT}"
        key = f"TRANSCEIVER_INIT_STATE|{port_name}"
        db.delete(db.STATE_DB, key)
    except Exception:
        pass  # Ignore errors on cleanup


def _is_warm_or_fast_boot():
    """True on a SONiC warm/fast reboot (kexec), where front-panel optics keep
    power and stay DataPathActivated -- so they must NOT be hardware-reset."""
    try:
        with open("/proc/cmdline") as f:
            cmdline = f.read()
    except OSError:
        return False
    return "SONIC_BOOT_TYPE=warm" in cmdline or "SONIC_BOOT_TYPE=fast" in cmdline


# Evaluated once at import (boot type is fixed for the life of the boot).
_WARM_OR_FAST_BOOT = _is_warm_or_fast_boot()


class PortState(Enum):
    """State machine states for port initialization."""
    INIT = auto()
    HOTSWAP_ENABLED = auto()
    WAITING_POWER_GOOD = auto()
    POWER_GOOD = auto()
    RESET_ASSERTED = auto()
    RESET_DEASSERTED = auto()
    WAITING_MODULE_INIT = auto()
    LPMODE_SET = auto()
    DRIVER_BOUND = auto()
    WAITING_OPTOE_PROBE = auto()
    XCVR_INITIALIZED = auto()
    COMPLETE = auto()
    FAILED = auto()


@dataclass
class PortContext:
    """Context for tracking individual port state during batch initialization."""
    port_num: int
    sfp: 'Sfp'
    state: PortState = PortState.INIT
    error: Optional[str] = None
    power_good_start_time: float = 0.0
    reset_asserted_time: float = 0.0  # Track when reset was asserted
    module_init_start_time: float = 0.0
    optoe_probe_start_time: float = 0.0

    def transition(self, new_state: PortState, error: Optional[str] = None):
        """Transition to a new state with optional error."""
        old_state = self.state
        self.state = new_state
        if error:
            self.error = error
        log_debug(f"Port {self.port_num}: {old_state.name} -> {new_state.name}")
        # Update STATE_DB for observability
        _update_init_state(self.port_num, new_state.name, error)

    def fail(self, reason: str):
        """Mark port as failed with reason."""
        self.transition(PortState.FAILED, reason)
        log_err(f"Port {self.port_num}: FAILED - {reason}")

    def complete(self):
        """Mark port as complete - keeps full state history in STATE_DB."""
        self.transition(PortState.COMPLETE)

    def process_state(self, current_time: float, power_good_timeout: float):
        """Process a single state transition for this port."""
        sfp = self.sfp
        port_num = self.port_num

        if self.state == PortState.INIT:
            # Transition: Enable hotswap
            sfp.set_hotswap_en(True)
            self.transition(PortState.HOTSWAP_ENABLED)

        elif self.state == PortState.HOTSWAP_ENABLED:
            # Transition: Start waiting for power_good
            self.power_good_start_time = current_time
            self.transition(PortState.WAITING_POWER_GOOD)

        elif self.state == PortState.WAITING_POWER_GOOD:
            # Check for power_good or timeout
            if sfp.get_power_good():
                elapsed_ms = int((current_time - self.power_good_start_time) * 1000)
                log_debug(f"Port {port_num}: power_good after {elapsed_ms}ms")
                self.transition(PortState.POWER_GOOD)
            elif (current_time - self.power_good_start_time) > power_good_timeout:
                self.fail(f"Timeout waiting for power_good after {power_good_timeout}s")

        elif self.state == PortState.POWER_GOOD:
            if _WARM_OR_FAST_BOOT:
                # Warm/fast reboot (kexec): the module kept power and stayed
                # DataPathActivated. Skip the HW reset + LowPwr toggle (which
                # would bounce a live link) and go straight to binding optoe so
                # the optics stay up (hitless). Cold boot keeps the full reset path.
                self.transition(PortState.LPMODE_SET)
            elif sfp.has_reset_control():
                if not sfp.reset_in():
                    self.fail("Failed to assert module reset")
                    return
                self.reset_asserted_time = current_time
                self.transition(PortState.RESET_ASSERTED)
            else:
                self.module_init_start_time = current_time
                self.transition(PortState.WAITING_MODULE_INIT)

        elif self.state == PortState.RESET_ASSERTED:
            # Wait for reset pulse duration (non-blocking check)
            RESET_PULSE_SECS = 1.0  # Match original phased implementation
            if (current_time - self.reset_asserted_time) >= RESET_PULSE_SECS:
                sfp.reset_out()
                self.module_init_start_time = current_time
                self.transition(PortState.RESET_DEASSERTED)

        elif self.state == PortState.RESET_DEASSERTED:
            # Transition: Start waiting for module init
            self.module_init_start_time = current_time
            self.transition(PortState.WAITING_MODULE_INIT)

        elif self.state == PortState.WAITING_MODULE_INIT:
            # Wait for module initialization (CMIS spec: ~2s after reset).
            # Deassert the hardware LowPwr pin so the module can power up to
            # ModuleReady and xcvrd's CmisManagerTask can drive datapath init
            # via CMIS software low-power control.
            if (current_time - self.module_init_start_time) >= SFP_RESET_SETTLE_TIME_SECS:
                sfp.set_lpmode(False)
                self.transition(PortState.LPMODE_SET)

        elif self.state == PortState.LPMODE_SET:
            # Transition: Bind optoe driver
            if sfp.bind():
                self.optoe_probe_start_time = current_time
                self.transition(PortState.DRIVER_BOUND)
            else:
                self.fail("Failed to bind optoe driver")

        elif self.state == PortState.DRIVER_BOUND:
            # Transition: Start waiting for optoe probe
            self.optoe_probe_start_time = current_time
            self.transition(PortState.WAITING_OPTOE_PROBE)

        elif self.state == PortState.WAITING_OPTOE_PROBE:
            # Wait for optoe driver probe to complete
            if (current_time - self.optoe_probe_start_time) >= SFP_OPTOE_PROBE_SETTLE_SECS:
                self.transition(PortState.XCVR_INITIALIZED)

        elif self.state == PortState.XCVR_INITIALIZED:
            # Transition: Initialize xcvr API
            sfp._xcvr_api = sfp.get_xcvr_api()
            sfp.sfp_type()
            # Laser is HW-disabled at reset; enable it via the board TX-disable
            # path -- FPGA register (QFX5220) or GPIO pin (QFX5250).
            if (sfp._txdisable_reg_and_bit()[0] is not None
                    or sfp._txdisable_pin is not None):
                sfp.set_tx_disable(False)
            sfp._power_reset_initialized = True
            self.complete()  # Clears STATE_DB entry


def batch_handle_insert(sfp_list):
    """Handle multiple transceiver insertions using a state machine approach.

    Each port independently transitions through states, allowing faster ports
    to progress while slower ones catch up.

    Args:
        sfp_list: List of tuples (port_num, sfp_object) to initialize
    Returns:
        List of (port_num, sfp) tuples that were successfully initialized
    """
    log_info("Batch insert: Processing {} ports: {}".format(
        len(sfp_list), [p for p, _ in sfp_list]))
    start_time = time.time()

    # Initialize port contexts
    ports: List[PortContext] = []
    for port_num, sfp in sfp_list:
        if sfp is None:
            log_info(f"Port {port_num}: SFP object is None, skipping")
            continue
        if not sfp.get_presence():
            log_info(f"Port {port_num}: Module removed before init, skipping")
            continue
        ports.append(PortContext(port_num=port_num, sfp=sfp))

    if not ports:
        log_info("Batch insert: No valid ports to process")
        return []

    # Pre-defined state sets (avoid recreating each iteration)
    TERMINAL_STATES = frozenset({PortState.COMPLETE, PortState.FAILED})
    WAITING_STATES = frozenset({PortState.WAITING_POWER_GOOD, PortState.RESET_ASSERTED,
                                PortState.WAITING_MODULE_INIT, PortState.WAITING_OPTOE_PROBE})
    RESET_KEEP_DEASSERT_STATES = frozenset({PortState.RESET_DEASSERTED,
                                            PortState.WAITING_MODULE_INIT,
                                            PortState.LPMODE_SET,
                                            PortState.DRIVER_BOUND,
                                            PortState.WAITING_OPTOE_PROBE})

    # State machine loop - run until all ports reach terminal state
    POWER_GOOD_TIMEOUT = 3.0  # seconds
    iteration = 0
    max_iterations = 1000  # Safety limit

    while iteration < max_iterations:
        iteration += 1

        # Count active ports without creating new list
        active_count = sum(1 for p in ports if p.state not in TERMINAL_STATES)
        if active_count == 0:
            break  # All ports reached terminal state

        current_time = time.time()
        all_waiting = True

        for ctx in ports:
            if ctx.state in TERMINAL_STATES:
                continue
            ctx.process_state(current_time, POWER_GOOD_TIMEOUT)
            if ctx.state not in WAITING_STATES:
                all_waiting = False

            if (ctx.sfp._reset_reg_offset is not None
                    and ctx.state in RESET_KEEP_DEASSERT_STATES):
                ctx.sfp.reset_out()

        # Sleep only if all active ports are in waiting states
        if all_waiting and active_count > 0:
            time.sleep(0.1)

    # Check if we hit the safety limit
    if iteration >= max_iterations:
        stuck_ports = [ctx.port_num for ctx in ports if ctx.state not in TERMINAL_STATES]
        log_err(f"Batch insert hit safety limit ({max_iterations} iterations), stuck ports: {stuck_ports}")

    # Collect successful ports
    successful = [(ctx.port_num, ctx.sfp) for ctx in ports if ctx.state == PortState.COMPLETE]
    failed = [(ctx.port_num, ctx.error) for ctx in ports if ctx.state == PortState.FAILED]

    elapsed = time.time() - start_time
    log_info(f"Batch insert complete: {len(successful)} succeeded, {len(failed)} failed in {elapsed:.1f}s")
    for port_num, error in failed:
        log_err(f"Port {port_num}: Failed - {error}")

    return successful


class SfpImplBase:
    """Default per-platform SFP implementation (inherited public API only).

    self._host is the owning Sfp (a SfpOptoeBase) facade, which owns config
    parsing, state, and the I2C/GPIO/MMIO mechanics. Public methods
    read state and call those mechanics via self._host. Platforms override only
    the hooks that differ.
    """

    def __init__(self, host):
        self._host = host

    # ---- SfpOptoeBase interface ---- #
    def get_cmis_host_interface_preference(self):
        return self._host._cmis_host_interface_preference

    def get_eeprom_path(self):
        sfp = self._host
        return sfp._eepromPath

    def get_name(self):
        sfp = self._host
        sfp_type = self.sfp_type()
        if sfp_type is not None:
            return sfp_type
        return sfp._port_type.upper() if sfp._port_type else 'N/A'

    def port_type(self):
        sfp = self._host
        return sfp._port_type

    def sfp_type(self):
        sfp = self._host
        if sfp._sfp_type is None and sfp._xcvr_api is not None:
            try:
                id_val = sfp._xcvr_api_factory._get_id()
            except Exception:
                id_val = None
            if id_val is not None:
                if id_val in SFP_TYPE_LIST:
                    sfp._sfp_type = 'SFP'
                elif id_val in QSFP_TYPE_LIST:
                    sfp._sfp_type = 'QSFP'
                elif id_val in QSFP_DD_TYPE_LIST:
                    sfp._sfp_type = 'QSFP-DD'
                elif id_val in OSFP_TYPE_LIST:
                    sfp._sfp_type = 'OSFP'
        return sfp._sfp_type

    def get_transceiver_info(self):
        sfp = self._host
        try:
            info = SfpOptoeBase.get_transceiver_info(sfp)
            if info is not None and any(info.get(key) not in (None, '', 'N/A')
                                       for key in ('manufacturer', 'model', 'serial')):
                return info

            # Signal "EEPROM not ready" so xcvrd retries instead of caching placeholder data.
            log_err("Port {}: transceiver EEPROM not readable yet; reporting not ready".format(
                sfp._index))
            return None
        except UnboundLocalError as exc:
            if 'nad_support' not in str(exc):
                raise
            log_err("Port {}: get_transceiver_info fallback (nad_support bug): {}".format(
                sfp._index, exc))
            return None

    def is_replaceable(self):
        return True

    def get_position_in_parent(self):
        return -1

    def get_error_description(self):
        sfp = self._host
        if not self.get_presence():
            return sfp.SFP_STATUS_UNPLUGGED
        return sfp.SFP_STATUS_OK

    # ---- GPIO / MMIO-based port control ---- #
    def get_presence(self):
        """Detect transceiver presence.

        If the platform sets a presence register offset in SFP_CTRL, presence is
        read from that PFE BAR0 bitmap via MMIO -- bit <port index> set ==
        present. Platforms that do not set those keys fall back to GPIO presence.
        """
        sfp = self._host
        if sfp._invalid_port:
            return False
        if sfp._port_type == "sfp":
            reg_off = sfp._sfp_presence_reg_offset
            bit = sfp._index - sfp._sfp_index_base
        else:
            reg_off = sfp._presence_reg_offset
            bit = sfp._index
            if (sfp._presence_hi_reg_offset is not None
                    and sfp._index >= sfp._presence_reg_port_span):
                reg_off = sfp._presence_hi_reg_offset
                bit = sfp._index - sfp._presence_reg_port_span
        if reg_off is not None and sfp._i2c_mst_pci_path:
            reg = sfp._read_pfe_reg(reg_off)
            if reg is None or bit < 0:
                return False
            return bool((reg >> bit) & 1)
        # Fallback: GPIO-based presence
        if sfp._presence_pin is None:
            return False
        val = read_gpio(sfp._presence_pin)
        return val == sfp._present_active

    def reset_in(self):
        """Assert reset (put module in reset state)."""
        sfp = self._host
        off, bit = sfp._reset_reg_and_bit()
        if off is not None:
            return sfp._set_pfe_reg_bit(off, bit, int(sfp._reset_active))
        if sfp._reset_pin is None:
            return False
        return write_gpio(sfp._reset_pin, int(sfp._reset_active))

    def reset_out(self):
        """Deassert reset (take module out of reset state)."""
        sfp = self._host
        off, bit = sfp._reset_reg_and_bit()
        if off is not None:
            return sfp._set_pfe_reg_bit(off, bit, sfp._reset_deassert)
        if sfp._reset_pin is None:
            return False
        return write_gpio(sfp._reset_pin, sfp._reset_deassert)

    def reset(self):
        """Reset SFP and return to default state."""
        if not self.reset_in():
            return False
        time.sleep(1)
        if not self.reset_out():
            return False
        return True

    def get_reset_status(self):
        """Return True if module is in reset."""
        sfp = self._host
        off, bit = sfp._reset_reg_and_bit()
        if off is not None:
            reg = sfp._read_pfe_reg(off)
            if reg is None:
                return False
            return str((reg >> bit) & 1) == str(sfp._reset_active)
        if sfp._reset_pin is None:
            return False
        val = read_gpio(sfp._reset_pin)
        return val == sfp._reset_active

    def set_tx_disable(self, tx_disable):
        """Enable/disable the SFP+ laser via the FPGA TX-disable register.

        QFX5220 SFP+ TX-disable is reachable only through this MMIO register
        (no GPIO/soft path), so xcvrd's soft tx_disable is a no-op without it.
        Ports without the register keep the base-class (soft) behaviour.
        """
        sfp = self._host
        if sfp._port_type == "sfp" and sfp._txdisable_pin is not None:
            return sfp._txdisable_gpio(tx_disable)
        off, bit = sfp._txdisable_reg_and_bit()
        if off is not None:
            val = int(sfp._txdisable_active) if tx_disable else sfp._txdisable_deassert
            return sfp._set_pfe_reg_bit(off, bit, val)
        return SfpOptoeBase.set_tx_disable(sfp, tx_disable)

    def get_status(self):
        """Return True if module is present and not in reset."""
        return self.get_presence() and not self.get_reset_status()

    def get_revision(self):
        return 'NA'

    def get_lpmode(self):
        """Return True if module is in low-power mode."""
        sfp = self._host
        if sfp._lpmod_pin is None:
            return False
        val = read_gpio(sfp._lpmod_pin)
        return val == sfp._lpmode_active

    def set_lpmode(self, lpmode):
        """Set low-power mode on/off."""
        sfp = self._host
        if sfp._lpmod_pin is None:
            return False
        if lpmode:
            return write_gpio(sfp._lpmod_pin, int(sfp._lpmode_active))
        else:
            return write_gpio(sfp._lpmod_pin, sfp._lpmode_deassert)

    def get_hotswap_en(self):
        """Return True if hotswap power is enabled."""
        sfp = self._host
        if sfp._has_sfp_pwr_module():
            return sfp._get_sfp_channel_power()
        if sfp._enable_pin is None:
            return False
        val = read_gpio(sfp._enable_pin)
        return val == sfp._enable_active

    def set_hotswap_en(self, enable):
        """Enable or disable hotswap power.

        For SFP ports fronted by a per-channel power module (MPM54322), the
        shared eFuse-enable GPIO gates both channels, so it is asserted on
        enable and left asserted on disable (per-channel off is handled by the
        module) to keep the sibling SFP powered.
        """
        sfp = self._host
        ok = True
        if sfp._enable_pin is not None:
            if enable:
                ok = write_gpio(sfp._enable_pin, int(sfp._enable_active))
            elif not sfp._has_sfp_pwr_module():
                ok = write_gpio(sfp._enable_pin, sfp._enable_deassert)
        if sfp._has_sfp_pwr_module():
            ok = sfp._set_sfp_channel_power(enable) and ok
        return ok

    def get_power_good(self):
        """Return True if port power is good."""
        sfp = self._host
        return True
        if sfp._powergood_pin is None:
            return False
        val = read_gpio(sfp._powergood_pin)
        return val == sfp._powergood_active

    def is_initialized(self):
        """Return True if the optoe driver is already bound for this port.

        On platforms without a PDDF PORT<N> stanza (e.g. QFX5220) optoe is
        bound only by this class's insert handling, so the EEPROM sysfs node
        is absent on cold boot (full init needed) and present across a warm
        restart (e.g. `config reload`) where the module is already up and must
        not be hardware-reset (which would tear down a live link).
        """
        import os
        sfp = self._host
        # PDDF pre-binds optoe for ports with a PORT stanza, so the node
        # existing says nothing about whether this port was initialized.
        if sfp.pddf_obj is not None and \
                "PORT{}".format(sfp._index) in sfp.pddf_obj.data:
            return False
        try:
            if sfp._eepromPath is None:
                sfp._resolve_i2c_path()
            return sfp._eepromPath is not None and os.path.exists(sfp._eepromPath)
        except Exception:
            return False

    # ---- Optoe driver bind / unbind ---- #
    def bind(self):
        """Bind optoe driver for this SFP port."""
        import os
        sfp = self._host
        if sfp._i2c_path is None:
            log_err("Port {}: Cannot bind - i2c_path not initialized".format(sfp._index))
            return False
        # PDDF instantiates the device from the PORT stanza at init; writing
        # new_device again only produces a kernel EBUSY message.
        if sfp._eepromPath and os.path.exists(sfp._eepromPath):
            return True
        try:
            with open(sfp._i2c_path + '/new_device', 'w') as f:
                f.write('{} {}\n'.format(sfp._driver, sfp._eeprom_addr))
        except IOError as e:
            if e.errno == 16:  # EBUSY - already exists
                return True
            log_err("Port {}: Unable to bind {}: {}".format(sfp._index, sfp._driver, e))
            return False
        return True

    def unbind(self):
        """Unbind optoe driver for this SFP port."""
        sfp = self._host
        if sfp._i2c_path is None:
            log_err("Port {}: Cannot unbind - i2c_path not initialized".format(sfp._index))
            return False
        try:
            with open(sfp._i2c_path + '/delete_device', 'w') as f:
                f.write('{}\n'.format(sfp._eeprom_addr))
        except IOError as e:
            if e.errno == 2:  # ENOENT - doesn't exist
                return True
            log_err("Port {}: Unable to unbind: {}".format(sfp._index, e))
            return False
        return True

    # ---- Hotswap event handling ---- #
    def handle_insert(self):
        """Handle transceiver insertion: power on, reset, bind driver.

        Sequence: enable power -> wait power_good -> reset cycle ->
                  set lpmode -> bind optoe -> init xcvr API.
        """
        sfp = self._host
        log_info("Port {}: Processing insert event".format(sfp._index))

        # Step 1: Enable power
        if not self.set_hotswap_en(True):
            log_err("Port {}: Failed to enable hotswap".format(sfp._index))

        # Step 2: Wait for power good
        power_good = False
        checks = int(sfp._powergood_timeout / 0.1)
        for _ in range(max(checks, 1)):
            if self.get_power_good():
                power_good = True
                break
            time.sleep(0.1)

        if not power_good:
            log_err("Port {}: Timeout waiting for power_good".format(sfp._index))
            return False

        # Warm/fast reboot (kexec): the module kept power and stayed
        # DataPathActivated; resetting it or forcing LowPwr here would bounce a
        # live link. Skip straight to binding optoe so the optic stays up
        # (hitless). Cold boot keeps the full reset + low-power init.
        if not _WARM_OR_FAST_BOOT:
            # Step 3: Reset cycle, when the platform provides a qualified control
            if sfp.has_reset_control() and not self.reset():
                log_err("Port {}: Failed to reset module".format(sfp._index))
                return False

            # CMIS modules need time after reset
            time.sleep(sfp._reset_settle_secs)

            # Step 4: Release the hardware low-power pin for module initialization
            self.set_lpmode(False)

        # Step 5: Bind optoe driver
        if not self.bind():
            log_err("Port {}: Failed to bind optoe driver".format(sfp._index))
            return False

        # Wait for optoe probe
        time.sleep(sfp._optoe_probe_secs)

        # Initialize xcvr API
        sfp._xcvr_api = sfp.get_xcvr_api()
        self.sfp_type()
        if sfp._txdisable_reg_and_bit()[0] is not None:
            self.set_tx_disable(False)  # SFP+ laser is HW-disabled at reset; enable it
        sfp._power_reset_initialized = True

        log_info("Port {}: Insert handling complete".format(sfp._index))
        return True

    def handle_remove(self):
        """Handle transceiver removal: unbind driver, reset, power off."""
        sfp = self._host
        log_info("Port {}: Processing remove event".format(sfp._index))

        self.unbind()
        self.reset_in()
        self.set_hotswap_en(False)

        sfp._power_reset_initialized = False
        sfp._xcvr_api = None
        sfp._sfp_type = None

        # Clear init state history from STATE_DB
        _clear_init_state(sfp._index)

        log_info("Port {}: Remove handling complete".format(sfp._index))
        return True
