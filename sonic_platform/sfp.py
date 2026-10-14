#!/usr/bin/env python3
#
# Name: sfp.py, version: 3.0
#
# Description: Generic SFP/transceiver class for Juniper platforms.
#
# All hardware-specific configuration (GPIO labels, I2C prefixes, timing
# constants, active-level values) is read from pddf-device.json SFP_CTRL
# entry.  Zero hardcoded platform-specific values in this file.
#
# Extends SfpOptoeBase directly (not PddfSfp) because:
#   - Dynamic I2C bus discovery via supercon instance + mux is cleaner
#     than 36 PORT{N} JSON entries
#   - PDDF's get_gpio_attr_path() requires hardcoded gpio_base — incompatible
#     with dynamic GPIO bases from hotswap-supercon driver
#
# Copyright (c) 2024, Juniper Networks, Inc.
# All rights reserved.
#

try:
    import os
    import time
    import mmap
    import syslog
    from datetime import datetime
    from enum import Enum, auto
    from dataclasses import dataclass
    from typing import Optional, List
    from sonic_platform_base.sonic_xcvr.sfp_optoe_base import SfpOptoeBase
    from sonic_platform.gpio_helper import read_gpio, write_gpio, resolve_gpio_pin
    from sonic_platform.sysfs_util import find_i2c_bus, find_i2c_tmc_bus
    try:
        from swsscommon.swsscommon import SonicV2Connector
        HAS_SWSSCOMMON = True
    except ImportError:
        HAS_SWSSCOMMON = False
except ImportError as e:
    raise ImportError(str(e) + " - required module not found")

# Patch CmisApi.get_application_advertisement to fix UnboundLocalError on
# 'nad_support' when is_flat_memory() returns True. The upstream code assigns
# nad_support only inside 'if not self.is_flat_memory()' but uses it
# unconditionally in 'max_apsels = 16 + nad_support * 16'.
# Remove this patch once the fix is upstreamed in sonic-platform-common.
try:
    from sonic_platform_base.sonic_xcvr.api.public.cmis import CmisApi as _CmisApi
    _orig_get_app_adv = _CmisApi.get_application_advertisement
    def _safe_get_application_advertisement(self):
        try:
            return _orig_get_app_adv(self)
        except UnboundLocalError as _e:
            if 'nad_support' not in str(_e):
                raise
            return {}
    _CmisApi.get_application_advertisement = _safe_get_application_advertisement
except Exception:
    pass

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
        """
        Process a single state transition for this port.

        This method handles one state transition at a time, allowing the main loop
        to interleave processing across all ports.

        Args:
            current_time: Current timestamp for timeout calculations
            power_good_timeout: Timeout for power_good wait
        """
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
    """
    Handle multiple transceiver insertions using a state machine approach.

    Each port independently transitions through states, allowing faster ports
    to progress while slower ones catch up. This provides better parallelism
    and clearer failure handling.

    Args:
        sfp_list: List of tuples (port_num, sfp_object) to initialize

    Returns:
        List of (port_num, sfp) tuples that were successfully initialized

    TODO: Support dynamic port addition during batch processing to reduce
          latency for hot-inserted modules. This would involve:
          1. Accept a queue parameter to check for new events during wait states
          2. Add new PortContexts to the active list mid-batch
          3. Process them through remaining states without restarting the batch
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


class Sfp(SfpOptoeBase):
    """Generic SFP class — reads all config from pddf-device.json SFP_CTRL."""

    I2C_PATH = "/sys/bus/i2c/devices/i2c-{0}"
    EEPROM_BASE = I2C_PATH + "/{0}-0050/eeprom"

    def __init__(self, index, pddf_data=None, pddf_plugin_data=None):
        SfpOptoeBase.__init__(self)
        from sonic_platform.override import load_impl
        self._impl = load_impl("Sfp", self)
        # ---- Read config from JSON ----
        sfp_ctrl = {}
        base_gpio_attr = {}
        port_gpio_attr = {}
        if pddf_data is not None:
            sfp_ctrl = pddf_data.data.get('SFP_CTRL', {}).get('i2c', {}).get('dev_attr', {})
            base_gpio_attr = pddf_data.data.get('SFP_CTRL', {}).get('gpio_attr', {})
            port_data = pddf_data.data.get("PORT{}".format(index), {})
            port_gpio_attr = port_data.get('gpio_attr', {})

        # Effective per-port GPIO config: PORT<index>.gpio_attr overrides the
        # platform-wide SFP_CTRL.gpio_attr (shallow merge, port keys win).
        gpio_attr = {**base_gpio_attr, **port_gpio_attr}

        self.pddf_obj = pddf_data
        self._index = index
        self._num_ports = int(sfp_ctrl.get('num_ports', '36'))
        self._port_type = self._get_port_type(sfp_ctrl)
        self._default_driver = sfp_ctrl.get('default_driver', 'optoe3')
        self._i2c_mst_prefix = sfp_ctrl.get('i2c_mst_name_prefix', 'i2c-supercon.21:')
        self._ports_per_sc = int(sfp_ctrl.get('ports_per_supercon_instance', '2'))
        self._ports_per_tmc = sfp_ctrl.get('ports_per_tmc_channel')
        self._i2c_mst_pci_path = sfp_ctrl.get('i2c_mst_pci_path', '')
        self._eeprom_addr = sfp_ctrl.get('eeprom_addr', '0x50')
        self._sfp_ctrl_attr = sfp_ctrl
        self._gpio_attr = gpio_attr

        # Optional MMIO register-based presence (PFE BAR0 bitmap).
        # When set in SFP_CTRL, presence is read from the register bit instead
        # of GPIO; platforms that omit these keys keep the GPIO path unchanged.
        self._presence_reg_offset = self._parse_offset(sfp_ctrl.get('presence_reg_offset'))
        self._sfp_presence_reg_offset = self._parse_offset(sfp_ctrl.get('sfp_presence_reg_offset'))
        self._presence_hi_reg_offset = self._parse_offset(sfp_ctrl.get('presence_hi_reg_offset'))
        self._presence_reg_port_span = int(sfp_ctrl.get('presence_reg_port_span', self._num_ports))

        # Optional MMIO register-based reset (same PFE BAR as presence).
        self._reset_reg_offset = self._parse_offset(sfp_ctrl.get('reset_reg_offset'))
        self._reset_hi_reg_offset = self._parse_offset(sfp_ctrl.get('reset_hi_reg_offset'))
        self._reset_reg_port_span = int(sfp_ctrl.get('reset_reg_port_span', self._num_ports))

        # Optional register-based SFP+ TX-disable (same PFE BAR).
        # QFX5220: 0x32c TMC_PFE_SLAVE1_SFP_TXDISABLE, bit = index - sfp_index_base;
        # bit == txdisable_active_value (1) holds the laser off.  No GPIO/soft path
        # reaches this line, so it must be driven via MMIO or the laser stays off.
        self._sfp_txdisable_reg_offset = self._parse_offset(sfp_ctrl.get('sfp_txdisable_reg_offset'))

        sfp_range_cfg = sfp_ctrl.get('sfp_port_range', '')
        self._sfp_index_base = int(sfp_range_cfg.split('-')[0]) if sfp_range_cfg else 0

        # Per-port GPIO stride (for packed GPIO banks with multiple signals per port).
        # Default stride=1/bit=0 preserves 1-GPIO-per-port behaviour.
        self._gpio_offset = gpio_attr.get("gpio_offset")
        self._gpio_stride = int(gpio_attr.get('gpio_port_stride', '1'))
        self._gpio_bits = {
            '_presence_pin': int(gpio_attr.get('gpio_presence_bit', '0')),
            '_reset_pin': int(gpio_attr.get('gpio_reset_bit', '0')),
            '_lpmod_pin': int(gpio_attr.get('gpio_lpmode_bit', '0')),
            '_txdisable_pin': int(gpio_attr.get('gpio_txdisable_bit', '0')),
            '_rxloss_pin': int(gpio_attr.get('gpio_rxlos_bit', '0')),
            '_enable_pin': int(gpio_attr.get('gpio_enable_bit', '0')),
            '_powergood_pin': int(gpio_attr.get('gpio_powergood_bit', '0')),
        }

        # GPIO labels
        self._gpio_presence_label = self._resolve_gpio_label(gpio_attr, "presence")
        self._gpio_lpmode_label = self._resolve_gpio_label(gpio_attr, "lpmode")
        self._gpio_reset_label = self._resolve_gpio_label(gpio_attr, "reset")
        self._gpio_txdisable_label = self._resolve_gpio_label(gpio_attr, "txdisable")
        self._gpio_rxloss_label = self._resolve_gpio_label(gpio_attr, "rxlos")
        self._gpio_enable_label = self._resolve_gpio_label(gpio_attr, "enable")
        self._gpio_powergood_label = self._resolve_gpio_label(gpio_attr, "powergood")

        # Active-level values (what '1' or '0' means for each function)
        self._present_active = gpio_attr.get('present_active_value', '1')
        self._lpmode_active = gpio_attr.get('lpmode_active_value', '1')
        self._reset_active = gpio_attr.get('reset_active_value', '0')
        self._txdisable_active = gpio_attr.get('txdisable_active_value', '0')
        self._rxloss_active = gpio_attr.get('rxloss_active_value', '0')
        self._enable_active = gpio_attr.get('enable_active_value', '1')
        self._powergood_active = gpio_attr.get('powergood_active_value', '1')

        # Timing constants
        self._reset_settle_secs = float(sfp_ctrl.get('reset_settle_time_secs', '2.0'))
        self._optoe_probe_secs = float(sfp_ctrl.get('optoe_probe_settle_secs', '3.0'))
        self._powergood_timeout = float(sfp_ctrl.get('powergood_timeout_secs', '3.0'))

        self._cmis_host_interface_preference = sfp_ctrl.get('cmis_host_interface_preference') or None
        # Optional per-channel SFP power module (e.g. MPM54322). When present,
        # SFP ports get independent power via the module's per-channel hwmon
        # enable attribute (out<N>_enable) instead of only the shared
        # eFuse-enable GPIO, which gates every SFP channel together. Platforms
        # that omit this key keep the GPIO-only path unchanged.
        # PDDF device name whose parent_bus/dev_addr locate the module.
        self._sfp_pwr_device = sfp_ctrl.get('sfp_pwr_device')
        # Resolved bus/address are cached after the first lookup.
        self._sfp_pwr_bus = None
        self._sfp_pwr_addr = None

        # ---- Instance state ----
        #self._index = index
        self._slot = 0
        self._invalid_port = False
        self._sfp_type = None
        self._driver = sfp_ctrl.get("sfp_driver") if self._port_type == "sfp" \
                   else sfp_ctrl.get("default_driver", "optoe3")
        self._power_reset_initialized = False
        self._mux_bus = None
        self._i2c_path = None
        self._eepromPath = None

        # GPIO pin numbers (absolute = gpiochip_base + port_offset)
        self._presence_pin = None
        self._reset_pin = None
        self._lpmod_pin = None
        self._enable_pin = None
        self._powergood_pin = None
        self._txdisable_pin = None
        self._rxloss_pin = None

        # Pre-compute deassert values — avoids per-call string comparison
        # in reset_out(), set_lpmode(False), set_hotswap_en(False), set_txdisable(False).
        # Deassert = OPPOSITE of active (write the inverse to deactivate)
        self._reset_deassert = 0 if self._reset_active == '1' else 1
        self._lpmode_deassert = 0 if self._lpmode_active == '1' else 1
        self._enable_deassert = 0 if self._enable_active == '1' else 1
        self._txdisable_deassert = 0 if self._txdisable_active == '1' else 1

        # Validate port index
        if index < 0 or index >= self._num_ports:
            log_err("Invalid port index {}: must be 0-{}".format(index, self._num_ports - 1))
            self._invalid_port = True
            return

        # ---- Resolve I2C bus for this port ----
        self._resolve_i2c_path()

        # ---- Resolve GPIO pins for this port ----
        self._resolve_gpio_pins()

    def _resolve_i2c_path(self):
        sfp_ctrl = self.pddf_obj.data.get("SFP_CTRL", {}).get("i2c", {}).get("dev_attr", {})
        pci_path = sfp_ctrl.get("i2c_mst_pci_path")
        prefix = sfp_ctrl.get("i2c_mst_name_prefix")

        if pci_path and self._ports_per_tmc:
            # TMC model: single I2C master with N mux channels.
            # Discover adapter via PCI sysfs, port index = mux channel.
            tmc_bus = find_i2c_tmc_bus(pci_path)
            if tmc_bus is None:
                log_err("Port {}: TMC I2C adapter not found under '{}'".format(
                    self._index, pci_path))
                return

            mux_name = "i2c-{}-mux (chan_id {})".format(tmc_bus, self._index)
            mux_bus = find_i2c_bus(mux_name)
            if mux_bus is None:
                log_err("Port {}: Mux channel '{}' not found".format(self._index, mux_name))
                return
        elif prefix:
            # PTX path: compute from Supercon formula
            sc_instance = self._index // self._ports_per_sc
            chan_id = self._index % self._ports_per_sc
            adapter_name = "{}{}".format(self._i2c_mst_prefix, sc_instance)

            sc_bus = find_i2c_bus(adapter_name)
            if sc_bus is None:
                log_err("Port {}: I2C adapter '{}' not found".format(self._index, adapter_name))
                return

            mux_name = "i2c-{}-mux (chan_id {})".format(sc_bus, chan_id)
            mux_bus = find_i2c_bus(mux_name)
            if mux_bus is None:
                log_err("Port {}: Mux channel '{}' not found".format(self._index, mux_name))
                return
        else:
            # Vanilla PDDF stores literal parent_bus numbers in JSON.
            port_data = self.pddf_obj.data.get("PORT{}".format(self._index), {})
            parent_bus = port_data.get("i2c", {}).get("topo_info", {}).get("parent_bus", "0x0")
            try:
                mux_bus = int(str(parent_bus), 0)
            except (TypeError, ValueError):
                resolver = getattr(self.pddf_obj, "bus_resolver", None)
                if resolver is None:
                    log_err("Port {}: invalid literal parent_bus '{}'".format(
                        self._index, parent_bus))
                    return
                try:
                    mux_bus = resolver.resolve_parent_bus(parent_bus)
                except Exception as exc:
                    log_err("Port {}: bus resolve failed for '{}': {}".format(
                        self._index, parent_bus, exc))
                    return
            if mux_bus is None:
                return

        self._mux_bus = mux_bus
        self._i2c_path = self.I2C_PATH.format(mux_bus)
        self._eepromPath = self.EEPROM_BASE.format(mux_bus)

    def _port_in_range(self, range_str):
        if not range_str:
            return False
        try:
            start, end = map(int, range_str.split("-"))
        except ValueError:
            return False
        return start <= self._index <= end

    def _resolve_gpio_label(self, sfp_ctrl_attr, function_name):
        # 1. Single label covers every port (PTX / simple platforms).
        label = sfp_ctrl_attr.get("gpio_{}_label".format(function_name))
        if label:
            return label
        # 2. Range-split label group, read straight from JSON 'gpio_label_groups':
        #    a port in a group's range uses gpio_<func>_label_<suffix>.
        for group in sfp_ctrl_attr.get("gpio_label_groups", []):
            if self._port_in_range(group.get("port_range", "")):
                lbl = sfp_ctrl_attr.get(
                    "gpio_{}_label_{}".format(function_name, group.get("suffix", "")))
                if lbl:
                    return lbl
                break
        # 3. Port-type specific label, falling back to the legacy "osfp" key used
        #    by platforms that predate port_type being declared in SFP_CTRL.
        port_type = self._get_port_type(self._sfp_ctrl_attr)
        label = sfp_ctrl_attr.get("gpio_{}_label_{}".format(function_name, port_type))
        if not label and port_type not in ("osfp", "sfp"):
            label = sfp_ctrl_attr.get("gpio_{}_label_osfp".format(function_name))
        return label or ""

    def _get_port_type(self, sfp_ctrl_attr):
        sfp_range = sfp_ctrl_attr.get("sfp_port_range", "")
        if sfp_range:
            start, end = map(int, sfp_range.split("-"))
            if start <= self._index <= end:
                return "sfp"
        return sfp_ctrl_attr.get("port_type", "osfp").lower()

    def _gpio_signal_offset(self, attr):
        """GPIO line offset within its gpiochip for this port.

        Uses the explicit per-port 'gpio_offset' from the PORT<index> stanza
        when present. Grouped GPIO chips use an offset local to the matching
        port range; ungrouped chips use the port index.
        """
        signal_bit = self._gpio_bits.get(attr, 0)
        if self._gpio_offset is not None:
            return int(self._gpio_offset) + signal_bit
        for group in self._gpio_attr.get('gpio_label_groups', []):
            try:
                start, end = map(int, group.get('port_range', '').split('-'))
            except (AttributeError, TypeError, ValueError):
                continue
            if start <= self._index <= end:
                return ((self._index - start) * self._gpio_stride
                        + signal_bit)
        return self._index * self._gpio_stride + signal_bit

    def _resolve_gpio_pins(self):
        """Resolve absolute GPIO pin numbers from labels + per-signal offset."""
        label_map = [
            ('_presence_pin', self._gpio_presence_label),
            ('_reset_pin', self._gpio_reset_label),
            ('_lpmod_pin', self._gpio_lpmode_label),
            ('_txdisable_pin', self._gpio_txdisable_label),
            ('_rxloss_pin', self._gpio_rxloss_label),
            ('_enable_pin', self._gpio_enable_label),
            ('_powergood_pin', self._gpio_powergood_label),
        ]
        for attr, label in label_map:
            if not label:
                continue
            pin = resolve_gpio_pin(label, self._gpio_signal_offset(attr))
            if pin is not None:
                setattr(self, attr, pin)
            else:
                log_err("Port {}: gpiochip not found for label '{}'".format(
                    self._index, label))

    def get_cmis_host_interface_preference(self):
        return self._impl.get_cmis_host_interface_preference()

    def get_eeprom_path(self):
        return self._impl.get_eeprom_path()

    def get_name(self):
        return self._impl.get_name()

    def port_type(self):
        return self._impl.port_type()

    def sfp_type(self):
        return self._impl.sfp_type()

    def get_transceiver_info(self):
        return self._impl.get_transceiver_info()

    def is_replaceable(self):
        return self._impl.is_replaceable()

    def get_position_in_parent(self):
        return self._impl.get_position_in_parent()

    def get_error_description(self):
        return self._impl.get_error_description()

    def get_presence(self):
        return self._impl.get_presence()

    @staticmethod
    def _parse_offset(val):
        """Parse a hex/dec register-offset string to int; None if unset/invalid."""
        try:
            return int(val, 0) if val is not None else None
        except (TypeError, ValueError):
            return None

    def _read_pfe_reg(self, offset):
        """Read one 32-bit PFE BAR0 register (MMIO). None on failure."""
        if not self._i2c_mst_pci_path:
            return None
        path = "{}/resource0".format(self._i2c_mst_pci_path)
        try:
            fd = os.open(path, os.O_RDONLY)
        except OSError:
            return None
        try:
            page = offset & ~(mmap.PAGESIZE - 1)
            rel = offset - page
            mm = mmap.mmap(fd, rel + 4, mmap.MAP_SHARED,
                           mmap.PROT_READ, offset=page)
            try:
                return int.from_bytes(mm[rel:rel + 4], "little")
            finally:
                mm.close()
        except (OSError, ValueError):
            return None
        finally:
            os.close(fd)

    def _write_pfe_reg(self, offset, value):
        """Write one full 32-bit PFE BAR0 register (MMIO). False on failure."""
        if not self._i2c_mst_pci_path:
            return False
        path = "{}/resource0".format(self._i2c_mst_pci_path)
        try:
            fd = os.open(path, os.O_RDWR)
        except OSError:
            return False
        try:
            page = offset & ~(mmap.PAGESIZE - 1)
            rel = offset - page
            mm = mmap.mmap(fd, rel + 4, mmap.MAP_SHARED,
                           mmap.PROT_READ | mmap.PROT_WRITE, offset=page)
            try:
                mm[rel:rel + 4] = (value & 0xFFFFFFFF).to_bytes(4, "little")
                return True
            finally:
                mm.close()
        except (OSError, ValueError):
            return False
        finally:
            os.close(fd)

    def _set_pfe_reg_bit(self, offset, bit, value):
        """Read-modify-write a single bit of a PFE BAR0 register. False on failure."""
        if not self._i2c_mst_pci_path:
            return False
        path = "{}/resource0".format(self._i2c_mst_pci_path)
        try:
            fd = os.open(path, os.O_RDWR)
        except OSError:
            return False
        try:
            page = offset & ~(mmap.PAGESIZE - 1)
            rel = offset - page
            mm = mmap.mmap(fd, rel + 4, mmap.MAP_SHARED,
                           mmap.PROT_READ | mmap.PROT_WRITE, offset=page)
            try:
                cur = int.from_bytes(mm[rel:rel + 4], "little")
                new = (cur | (1 << bit)) if value else (cur & ~(1 << bit))
                if new != cur:
                    mm[rel:rel + 4] = (new & 0xFFFFFFFF).to_bytes(4, "little")
                return True
            finally:
                mm.close()
        except (OSError, ValueError):
            return False
        finally:
            os.close(fd)

    def _reset_reg_and_bit(self):
        """Return (reg_offset, bit) for this port's reset control, or (None, None)."""
        if self._reset_reg_offset is None or self._port_type == "sfp":
            return None, None
        off = self._reset_reg_offset
        bit = self._index
        if (self._reset_hi_reg_offset is not None
                and self._index >= self._reset_reg_port_span):
            off = self._reset_hi_reg_offset
            bit = self._index - self._reset_reg_port_span
        return off, bit

    def has_reset_control(self):
        """Return whether this port has a configured reset control."""
        off, _ = self._reset_reg_and_bit()
        return off is not None or self._reset_pin is not None

    def reset_in(self):
        return self._impl.reset_in()

    def reset_out(self):
        return self._impl.reset_out()

    def reset(self):
        """Reset SFP and return to default state."""
        if not self.reset_in():
            return False
        time.sleep(1)
        if not self.reset_out():
            return False
        return True

    def get_reset_status(self):
        return self._impl.get_reset_status()

    def _txdisable_reg_and_bit(self):
        """Return (reg_offset, bit) for this SFP+ port's TX-disable, or (None, None)."""
        if self._sfp_txdisable_reg_offset is None or self._port_type != "sfp":
            return None, None
        return self._sfp_txdisable_reg_offset, self._index - self._sfp_index_base

    def _txdisable_gpio(self, disable):
        """Drive the SFP TX-disable GPIO pin (disable=True asserts TX-off)."""
        value = int(self._txdisable_active) if disable else self._txdisable_deassert
        return write_gpio(self._txdisable_pin, value)

    def set_tx_disable(self, tx_disable):
        return self._impl.set_tx_disable(tx_disable)

    def get_status(self):
        return self._impl.get_status()

    def get_revision(self):
        return self._impl.get_revision()

    def get_lpmode(self):
        return self._impl.get_lpmode()

    def set_lpmode(self, lpmode):
        return self._impl.set_lpmode(lpmode)

    def get_hotswap_en(self):
        return self._impl.get_hotswap_en()

    def set_hotswap_en(self, enable):
        return self._impl.set_hotswap_en(enable)

    # ---- Per-channel SFP power module (MPM54322) ----

    def _has_sfp_pwr_module(self):
        """True when this SFP port uses a per-channel power module."""
        return (self._port_type == "sfp"
                and self._sfp_pwr_device is not None)

    def _sfp_pwr_channel(self):
        """1-based module output channel for this SFP (port64->1, port65->2)."""
        return (self._index - self._sfp_index_base) + 1

    def _resolve_sfp_pwr_dev(self):
        """Resolve and cache (bus, addr) of the power module's i2c device.

        The module is declared in pddf-device.json as the device named
        sfp_pwr_device (e.g. "VRM12"); use literal bus numbers directly and
        retain resolver support for platform configs with symbolic buses.
        """
        if self._sfp_pwr_bus is not None:
            return self._sfp_pwr_bus, self._sfp_pwr_addr
        dev = self.pddf_obj.data.get(self._sfp_pwr_device, {})
        topo = dev.get("i2c", {}).get("topo_info", {})
        parent_bus = topo.get("parent_bus")
        addr = topo.get("dev_addr")
        if parent_bus is None or addr is None:
            log_err("Port {}: {} device not found in PDDF config".format(
                self._index, self._sfp_pwr_device))
            return None, None
        try:
            bus = int(str(parent_bus), 0)
        except (TypeError, ValueError):
            resolver = getattr(self.pddf_obj, "bus_resolver", None)
            if resolver is None:
                log_err("Port {}: invalid parent_bus '{}' for {}".format(
                    self._index, parent_bus, self._sfp_pwr_device))
                return None, None
            try:
                bus = resolver.resolve_parent_bus(parent_bus)
            except Exception as exc:
                log_err("Port {}: {} bus resolve failed for '{}': {}".format(
                    self._index, self._sfp_pwr_device, parent_bus, exc))
                return None, None
        if bus is None:
            return None, None
        self._sfp_pwr_bus = bus
        self._sfp_pwr_addr = int(addr, 0)
        return self._sfp_pwr_bus, self._sfp_pwr_addr

    def _sfp_pwr_enable_path(self):
        """sysfs path to this SFP's per-channel enable attribute on the module.

        The mpm54522 hwmon driver exposes out<N>_enable (N=1,2) and handles the
        register unlock/write/lock and PMIC master-enable internally, so we
        only toggle this port's channel.
        """
        bus, addr = self._resolve_sfp_pwr_dev()
        if bus is None:
            return None
        hwmon_dir = os.path.join(self.I2C_PATH.format(bus),
                                 "{}-{:04x}".format(bus, addr), "hwmon")
        attr = "out{}_enable".format(self._sfp_pwr_channel())
        try:
            for entry in os.listdir(hwmon_dir):
                path = os.path.join(hwmon_dir, entry, attr)
                if os.path.exists(path):
                    return path
        except OSError:
            pass
        log_err("Port {}: {} {} sysfs attribute not found".format(
            self._index, self._sfp_pwr_device, attr))
        return None

    def _set_sfp_channel_power(self, enable):
        """Independently enable/disable this SFP's power-module output channel."""
        path = self._sfp_pwr_enable_path()
        if path is None:
            return False
        try:
            with open(path, "w") as f:
                f.write("1" if enable else "0")
            return True
        except (OSError, IOError) as e:
            log_err("Port {}: {} channel {} power {} failed: {}".format(
                self._index, self._sfp_pwr_device, self._sfp_pwr_channel(),
                "enable" if enable else "disable", e))
            return False

    def _get_sfp_channel_power(self):
        """Return True if this SFP's power-module output channel is enabled."""
        path = self._sfp_pwr_enable_path()
        if path is None:
            return False
        try:
            with open(path) as f:
                return f.read().strip() == "1"
        except (OSError, IOError):
            return False

    def get_power_good(self):
        return self._impl.get_power_good()

    # ---- Optoe driver bind / unbind ----

    def is_initialized(self):
        return self._impl.is_initialized()

    def bind(self):
        return self._impl.bind()

    def unbind(self):
        return self._impl.unbind()

    # ---- Hotswap event handling ----

    def handle_insert(self):
        return self._impl.handle_insert()

    def handle_remove(self):
        return self._impl.handle_remove()
