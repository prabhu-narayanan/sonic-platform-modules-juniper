#!/usr/bin/env python3
#
# Name: chassis.py, version: 3.0
#
# Description: Generic PddfChassis wrapper with SFP hotswap event handling.
#
# PddfChassis.__init__ creates all device objects (SFP, PSU, FanDrawer,
# Thermal, Eeprom, VoltageSensor) from pddf-device.json topology and
# provides get_name/model/serial/base_mac/revision via EEPROM.
#
# This subclass adds:
#   - SFP worker thread for async insert/remove power sequencing
#   - get_change_event() for xcvrd SFP presence polling
#   - Batched SFP insert using state-machine pipeline
#   - Deferred presence reporting (only after init completes)
#   - PORT_TABLE population in APPL_DB (workaround when swss is not running)
#   - get_reboot_cause() reads BIOS NVRAM devmem registers
#   - set_status_led() / get_status_led() via /sys/class/leds/system/brightness
#   - get_thermal_manager() returns ThermalManager for thermalctld
#
# Copyright (c) 2024, Juniper Networks, Inc.
# All rights reserved.
#

try:
    import time
    import syslog
    import subprocess
    import threading
    import queue
    from typing import List
    from sonic_platform_pddf_base.pddf_chassis import PddfChassis
    from sonic_platform_base.chassis_base import ChassisBase
    from sonic_platform_base.sfp_base import SfpBase
    try:
        from swsscommon.swsscommon import SonicV2Connector
        HAS_SWSSCOMMON = True
    except ImportError:
        HAS_SWSSCOMMON = False
except ImportError as e:
    raise ImportError(str(e) + " - required module not found")

SYSLOG_IDENTIFIER = "Juniper-Chassis"

# SFP_CTRL dev_attr "presence_report_policy" values.
_PRESENCE_REPORT_AFTER_INIT = 'after_init'
_PRESENCE_REPORT_IMMEDIATE = 'immediate'

try:
    from .liquid_cooling import LiquidCooling
except ImportError:
    LiquidCooling = None

# Constants for PORT_TABLE population
LANES_PER_PORT = 8

# System LED sysfs path
_SYS_LED_PATH = '/sys/class/leds/system/brightness'
_SYS_LED_COLOR_MAP = {
    'off': 0,
    'red': 1,
    'green': 2,
    'amber': 3,
    'blinking green': 4,
}
_SYS_LED_VAL_MAP = {v: k for k, v in _SYS_LED_COLOR_MAP.items()}


def log_info(msg):
    syslog.openlog(SYSLOG_IDENTIFIER)
    syslog.syslog(syslog.LOG_INFO, msg)
    syslog.closelog()


class NullXcvrObject(SfpBase):
    # Placeholder SFP object for physical slots that have no transceiver cage.

    def get_presence(self):
        return False

    def get_transceiver_info(self):
        return None

    def get_transceiver_bulk_status(self):
        return None

    def get_transceiver_threshold_info(self):
        return None

    def get_transceiver_status(self):
        return None

    def get_transceiver_pm(self):
        return None

    def get_name(self):
        return "N/A"

    def get_model(self):
        return "N/A"

    def get_serial(self):
        return "N/A"

    def get_reset_status(self):
        return False

    def get_lpmode(self):
        return False

    def is_replaceable(self):
        return False

    def get_error_description(self):
        return "Not present"


class Chassis(PddfChassis):
    """Generic Chassis — extends PddfChassis with SFP hotswap support."""

    def __init__(self, pddf_data=None, pddf_plugin_data=None):
        self._asic_thermal = None
        self._config_db = None
        self._asic_sync_ready = False
        PddfChassis.__init__(self, pddf_data, pddf_plugin_data)

        # Built from pddf-device.json LEAK/PRESSURE/FLOW/HUMIDITY_SENSOR entries,
        # so this is empty on the air-cooled SKU.
        self._liquid_cooling = (
            LiquidCooling(pddf_data) if LiquidCooling is not None else None)
        # Set before the SFP worker thread starts, since the worker delegates.
        from sonic_platform.override import load_impl
        self._impl = load_impl("Chassis", self)

        # Cache eeprom reference for overrides
        self._sys_eeprom = self._eeprom

        # Read port count from JSON PLATFORM section
        num_ports = self.platform_inventory.get('num_ports', 0)
        self.PORT_START = 0
        self.PORT_END = num_ports - 1
        self._num_ports = num_ports

        # SFP event queue and worker thread for async handling
        self._sfp_event_queue = queue.Queue()

        sfp_ctrl = self.pddf_obj.data.get('SFP_CTRL', {}).get('i2c', {}).get('dev_attr', {})

        # "immediate" suits platforms whose presence signal is independent of
        # the EEPROM bus, so a transport error cannot mask an inserted module.
        self._report_presence_immediately = (
            str(sfp_ctrl.get('presence_report_policy', _PRESENCE_REPORT_AFTER_INIT))
            == _PRESENCE_REPORT_IMMEDIATE)

        # Logical ports without a PORT stanza hold no transceiver (copper/RJ45),
        # so replace the SFP object PddfChassis created for them with a null one.
        # Formula-based platforms without PORT stanzas are detected and left unchanged.
        data = self.pddf_obj.data
        uses_port_stanzas = any("PORT{}".format(i) in data
                                for i in range(len(self._sfp_list)))
        if uses_port_stanzas:
            for i in range(len(self._sfp_list)):
                if "PORT{}".format(i) not in data:
                    self._sfp_list[i] = NullXcvrObject()

        self._sfp_init_complete_queue = queue.Queue()  # Worker signals init completion here
        self._sfp_pending_init = set()  # Ports with pending init (detected but not yet ready)
        self._sfp_worker_running = True
        self._sfp_worker = threading.Thread(
            target=self._sfp_event_worker, daemon=True
        )
        self._sfp_worker.start()

        # Track SFP presence state for change detection
        self.xcvr_presence_map = {}
        for port in range(self.PORT_START, self.PORT_END + 1):
            self.xcvr_presence_map[port] = '0'

        # Pre-cache SFP object references for the polling loop.
        # Avoids calling get_sfp() (which does bounds checking + method call
        # overhead) 36 times per 0.5s cycle.  Built as list of (index, sfp).
        self._sfp_poll_list = []
        for port in range(self.PORT_START, self.PORT_END + 1):
            sfp = self.get_sfp(port)
            if sfp is not None and not isinstance(sfp, NullXcvrObject):
                self._sfp_poll_list.append((port, sfp))

        # Initialize PORT_TABLE in APPL_DB (workaround when swss is not running)
        #self._init_port_table_db()

        # Append per-port optic thermal sensors to the thermal list
        self._init_sfp_thermals()

        self._asic_sync_ready = True
        self._sync_asic_thermal()

    def _asic_sensors_enabled(self):
        """Return whether orchagent's ASIC sensor poller is enabled."""
        if not HAS_SWSSCOMMON:
            return False
        try:
            if self._config_db is None:
                self._config_db = SonicV2Connector()
                self._config_db.connect(self._config_db.CONFIG_DB)
            return self._config_db.get(
                self._config_db.CONFIG_DB,
                "ASIC_SENSORS|ASIC_SENSORS_POLLER_STATUS",
                "admin_status") == "enable"
        except Exception as e:
            self._config_db = None
            log_info("_asic_sensors_enabled: CONFIG_DB check failed ({})".format(e))
            return False

    def _sync_asic_thermal(self):
        """Keep the ASIC thermal sensor aligned with CONFIG_DB poller state."""
        if not self._asic_sync_ready:
            return
        if self._asic_sensors_enabled():
            if self._asic_thermal is None:
                try:
                    from .asic_thermal import AsicThermal
                    self._asic_thermal = AsicThermal(
                        len(self._thermal_list), pddf_data=self.pddf_obj)
                except Exception as e:
                    log_info("_sync_asic_thermal: skipped ({})".format(e))
                    return
            if self._asic_thermal not in self._thermal_list:
                self._thermal_list.append(self._asic_thermal)
        elif self._asic_thermal is not None and self._asic_thermal in self._thermal_list:
            self._thermal_list.remove(self._asic_thermal)

    # ================================================================
    # Platform-API base overrides (ChassisBase / DeviceBase)
    # ================================================================
    # Required by the sonic-mgmt platform_api test suite. PddfChassis /
    # ChassisBase leave them unimplemented: the first two raise
    # NotImplementedError and get_watchdog returns the un-initialised
    # self._watchdog == None. The values below hold for every platform
    # sharing this file, all of which are fixed-configuration systems.

    def get_position_in_parent(self):
        """Return the chassis position in its parent device.

        DeviceBase raises NotImplementedError. Every platform sharing this
        PDDF chassis is a fixed-configuration system with no parent
        container, so the position is not applicable.
        """
        return -1

    def is_replaceable(self):
        """Return whether the chassis itself is field-replaceable.

        DeviceBase raises NotImplementedError. On a fixed-configuration
        system only the FRUs inside it -- fan trays, PSUs, optics -- are
        replaceable, not the chassis.
        """
        return False

    def get_watchdog(self):
        """Return the watchdog device object (lazy singleton).

        ChassisBase.get_watchdog() only returns self._watchdog, which nothing
        populates, so the platform API saw None.
        """
        if self._watchdog is None:
            try:
                from sonic_platform.watchdog import Watchdog
                self._watchdog = Watchdog()
            except Exception as e:
                log_info("get_watchdog: watchdog unavailable ({})".format(e))
        return self._watchdog

    def get_all_sfps(self):
        return [sfp for sfp in self._sfp_list
                if sfp is not None and not isinstance(sfp, NullXcvrObject)]

    def get_num_sfps(self):
        return len(self.get_all_sfps())

    def _init_port_table_db(self):
        """
        Populate PORT_TABLE in APPL_DB as a workaround when swss is not running.
        This allows xcvrd and sfpshow to function without portsyncd.
        """
        log_info("_init_port_table_db: Starting PORT_TABLE initialization")

        if not HAS_SWSSCOMMON:
            log_info("_init_port_table_db: swsscommon not available, skipping")
            return

        db = None
        try:
            db = SonicV2Connector()
        except Exception as e:
            log_info("_init_port_table_db: Failed to create SonicV2Connector: {} ({})".format(
                e, type(e).__name__))
            return

        try:
            db.connect(db.APPL_DB)
        except Exception as e:
            log_info("_init_port_table_db: Failed to connect to APPL_DB: {} ({})".format(
                e, type(e).__name__))
            return

        try:
            existing_keys = db.keys(db.APPL_DB, "PORT_TABLE:Ethernet*")
            if existing_keys and len(existing_keys) >= self._num_ports:
                log_info("_init_port_table_db: Already populated with {} entries, skipping".format(
                    len(existing_keys)))
                return
            log_info("_init_port_table_db: Found {} existing entries, need {}".format(
                len(existing_keys) if existing_keys else 0, self._num_ports))
        except Exception as e:
            log_info("_init_port_table_db: Failed to query existing keys: {} ({})".format(
                e, type(e).__name__))
            return

        try:
            log_info("_init_port_table_db: Populating {} ports".format(self._num_ports))
            for port_idx in range(self._num_ports):
                port_name = "Ethernet{}".format(port_idx * LANES_PER_PORT)
                start_lane = (port_idx * LANES_PER_PORT) + 1
                lanes = ",".join(str(start_lane + i) for i in range(LANES_PER_PORT))
                db.set(db.APPL_DB, "PORT_TABLE:{}".format(port_name), "index", str(port_idx))
                db.set(db.APPL_DB, "PORT_TABLE:{}".format(port_name), "lanes", lanes)
                db.set(db.APPL_DB, "PORT_TABLE:{}".format(port_name), "speed", "800000")
                db.set(db.APPL_DB, "PORT_TABLE:{}".format(port_name), "admin_status", "up")
                db.set(db.APPL_DB, "PORT_TABLE:{}".format(port_name), "mtu", "9100")
            db.set(db.APPL_DB, "PORT_TABLE:PortConfigDone", "count", str(self._num_ports))
            log_info("_init_port_table_db: Successfully populated {} ports".format(self._num_ports))
        except Exception as e:
            log_info("_init_port_table_db: Failed during port population: {} ({})".format(
                e, type(e).__name__))

    def _sfp_event_worker(self):
        """
        Worker thread that handles SFP power/reset/bind operations.
        Uses batched pipelined processing for efficient multi-port initialization.
        """
        from sonic_platform.impl_base.sfp import batch_handle_insert
        log_info("SFP event worker thread started (batched pipeline mode)")
        BATCH_COLLECT_TIME = 0.5  # Wait 500ms to collect batch of events

        while self._sfp_worker_running:
            # Collect a batch of events
            insert_ports = []
            remove_ports = []
            event_count = 0  # Track actual get() calls for task_done()

            try:
                # Wait for first event
                port_num, event = self._sfp_event_queue.get(timeout=1.0)
                event_count += 1
                if event == 'insert':
                    insert_ports.append(port_num)
                else:
                    remove_ports.append(port_num)
            except queue.Empty:
                continue
            except Exception as e:
                log_info("SFP worker queue error: {}".format(e))
                continue

            # Collect more events for batching (non-blocking)
            batch_start = time.time()
            while (time.time() - batch_start) < BATCH_COLLECT_TIME:
                try:
                    port_num, event = self._sfp_event_queue.get(timeout=0.05)
                    event_count += 1
                    if event == 'insert':
                        if port_num not in insert_ports:
                            insert_ports.append(port_num)
                    else:
                        if port_num not in remove_ports:
                            remove_ports.append(port_num)
                except queue.Empty:
                    break

            try:
                # Process remove events first (quick, no batching benefit)
                for port_num in remove_ports:
                    try:
                        sfp = self.get_sfp(port_num)
                        if sfp is not None:
                            sfp.handle_remove()
                    except Exception as e:
                        log_info("Port {}: Remove exception: {}".format(port_num, e))

                # Filter out ports that were removed in same batch (rapid insert/remove)
                if remove_ports:
                    insert_ports = [p for p in insert_ports if p not in remove_ports]

                # Process insert events in batched pipeline
                if insert_ports:
                    # Build list of (port_num, sfp) tuples for batch processing
                    sfp_list = []
                    for port_num in insert_ports:
                        sfp = self.get_sfp(port_num)
                        if sfp is not None:
                            sfp_list.append((port_num, sfp))
                    if sfp_list:
                        successful = batch_handle_insert(sfp_list)
                        # Signal completion for each successful port
                        for port_num, sfp in successful:
                            self._sfp_init_complete_queue.put((port_num, True))
                            log_info("Port {}: Init complete, signaling ready".format(port_num))
                        # Signal failure for ports that didn't succeed
                        successful_ports = {p for p, _ in successful}
                        for port_num, sfp in sfp_list:
                            if port_num not in successful_ports:
                                self._sfp_init_complete_queue.put((port_num, False))
                                log_info("Port {}: Init failed, signaling not ready".format(port_num))
            except Exception as e:
                log_info("SFP worker batch processing error: {} ({})".format(e, type(e).__name__))

            # Call task_done() for ALL items we got from queue
            for _ in range(event_count):
                self._sfp_event_queue.task_done()

        log_info("SFP event worker thread stopped")

    # -------------------------------------------------------------------------
    # Reboot cause
    # -------------------------------------------------------------------------

    @staticmethod
    def _devmem_read(addr):
        """Read one byte from a physical address via busybox devmem.

        Returns the hex string (e.g. '0x04') on success, or None on failure.
        """
        try:
            result = subprocess.run(
                ['busybox', 'devmem', addr, '8'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    @staticmethod
    def _devmem_clear(addr):
        """Write 0xFF to addr to clear sticky reboot-cause bits."""
        try:
            subprocess.run(
                ['busybox', 'devmem', addr, '8', '0xFF'],
                capture_output=True, text=True, timeout=5
            )
        except Exception:
            pass

    def get_all_thermals(self):
        return self._impl.get_all_thermals()

    def get_num_thermals(self):
        return self._impl.get_num_thermals()

    def get_thermal_policy_thermals(self):
        return self.get_all_thermals() + self._sfp_thermals

    def get_revision(self):
        return self._impl.get_revision()

    def get_change_event(self, timeout):
        return self._impl.get_change_event(timeout)

    def get_reboot_cause(self):
        return self._impl.get_reboot_cause()

    # ================================================================
    # Per-port optic thermal sensors
    # ================================================================

    def _init_sfp_thermals(self):
        """Create optic sensors for thermal policy, separate from chassis sensors."""
        from .sfp_thermal import SfpThermal

        self._sfp_thermals = []
        optic_thresholds = {}
        try:
            optic_thresholds = self.pddf_obj.data.get('OPTIC_THRESHOLDS', {})
        except Exception:
            pass

        num_ports = self.platform_inventory.get('num_ports', 0)
        for i in range(num_ports):
            if i < len(self._sfp_list) and not isinstance(self._sfp_list[i], NullXcvrObject):
                sfp_thermal = SfpThermal(i, self._sfp_list[i], optic_thresholds)
                self._sfp_thermals.append(sfp_thermal)

    # -------------------------------------------------------------------------
    # Liquid cooling (OE-L): leak / pressure / flow / humidity, polled by
    # sensormond into LEAK_INFO / PRESSURE_INFO / FLOW_INFO / HUMIDITY_INFO.
    # -------------------------------------------------------------------------

    def get_liquid_cooling(self):
        """Liquid cooling subsystem, or None on air-cooled SKUs."""
        if self._liquid_cooling is None or not self._liquid_cooling.get_presence():
            return None
        return self._liquid_cooling

    def get_all_leak_sensors(self):
        lc = self.get_liquid_cooling()
        return lc.get_all_leak_sensors() if lc else []

    def get_all_pressure_sensors(self):
        lc = self.get_liquid_cooling()
        return lc.get_all_pressure_sensors() if lc else []

    def get_all_flow_sensors(self):
        lc = self.get_liquid_cooling()
        return lc.get_all_flow_sensors() if lc else []

    def get_all_humidity_sensors(self):
        lc = self.get_liquid_cooling()
        return lc.get_all_humidity_sensors() if lc else []

    # -------------------------------------------------------------------------
    # Thermal manager
    # -------------------------------------------------------------------------

    def get_thermal_manager(self):
        return self._impl.get_thermal_manager()

    SYS_LED_NAME = "SYS_LED"

    def initizalize_system_led(self):
        return self._impl.initizalize_system_led()

    def set_status_led(self, color):
        return self._impl.set_status_led(color)

    def get_status_led(self):
        return self._impl.get_status_led()

