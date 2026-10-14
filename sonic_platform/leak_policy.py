#!/usr/bin/env python3
#
# leak_policy.py — thermal-policy hooks for liquid cooling leak detection
#
# Registers one info, one condition and one action with the thermal policy
# framework, so a leak can raise alarms and ultimately shut the system down
# via the same engine that handles over-temperature.
#
# Alarm tiers follow the Junos EVO model for this board (capdb
# qfx5250_64oe_l_fpc_fdt.h, leakage_threshold):
#   score >  yat (0)   yellow alarm
#   score >= rat (5)   red alarm
#   score >= ft  (20)  shutdown -- opt-in via shutdown_enabled, default off
#
# A leak shutdown is drastic and hard to undo, so it requires the condition to
# persist for wait_interval seconds rather than firing on a single sample.
# That matters here: if the ADS1015 input range is left at the driver default
# the leak channels saturate at 2047 mV, which converts to a score of 22 --
# above ft -- on a completely dry system. qfx5250_post_pddf_init.py:adc_pga_init()
# sets the range correctly; the soak below is the second line of defence.
#
# Copyright (c) 2026, Juniper Networks, Inc.
# All rights reserved.

import subprocess
import time

try:
    from sonic_py_common import logger
    from sonic_platform_base.sonic_thermal_control.thermal_action_base import ThermalPolicyActionBase
    from sonic_platform_base.sonic_thermal_control.thermal_condition_base import ThermalPolicyConditionBase
    from sonic_platform_base.sonic_thermal_control.thermal_info_base import ThermalPolicyInfoBase
    from sonic_platform_base.sonic_thermal_control.thermal_json_object import thermal_json_object
except ImportError as e:
    raise ImportError(str(e) + ' - required module not found') from e

sonic_logger = logger.Logger('leak_policy')

LEAK_SHUTDOWN_WAIT_INTERVAL = 60


@thermal_json_object('leak_info')
class LeakInfo(ThermalPolicyInfoBase):
    """Leak sensor state for the policy engine."""

    INFO_NAME = 'leak_info'

    def __init__(self):
        self._leaking = []
        self._worst_score = None
        self._chassis = None

    def collect(self, chassis):
        self._chassis = chassis
        self._leaking = []
        self._worst_score = None

        getter = getattr(chassis, 'get_all_leak_sensors', None)
        if getter is None:
            return

        try:
            sensors = getter() or []
        except Exception as e:
            sonic_logger.log_warning(f"[LEAK] Failed to enumerate leak sensors: {e}")
            return

        for sensor in sensors:
            try:
                # An unreadable sensor is reported, never treated as a leak:
                # acting on None would shut the system down on an i2c glitch.
                score = sensor.get_value()
                if score is None:
                    sonic_logger.log_warning(
                        f"[LEAK] {sensor.get_name()} unreadable; ignoring for policy")
                    continue
                if sensor.is_leak():
                    self._leaking.append((sensor, score))
                if self._worst_score is None or score > self._worst_score:
                    self._worst_score = score
            except Exception as e:
                sonic_logger.log_warning(f"[LEAK] Error reading leak sensor: {e}")

    def get_leaking_sensors(self):
        return self._leaking

    def get_worst_score(self):
        return self._worst_score

    def get_chassis(self):
        return self._chassis


@thermal_json_object('leak.any.detected')
class AnyLeakDetectedCondition(ThermalPolicyConditionBase):
    """True while any leak sensor reports a leak."""

    def is_match(self, thermal_info_dict):
        info = thermal_info_dict.get(LeakInfo.INFO_NAME)
        if not isinstance(info, LeakInfo):
            return False
        return len(info.get_leaking_sensors()) > 0


@thermal_json_object('leak.always')
class LeakAlwaysCondition(ThermalPolicyConditionBase):
    """Always true, so the action can also clear alarms when a leak stops."""

    def is_match(self, thermal_info_dict):
        return True


@thermal_json_object('leak.shutdown_check')
class LeakShutdownAction(ThermalPolicyActionBase):
    """Raise leak alarms and shut down on a sustained critical leak.

    JSON example:
        {
            "type": "leak.shutdown_check",
            "wait_interval": "60",
            "shutdown_enabled": "false"
        }

    wait_interval is how long a score at or above the shutdown threshold must
    persist before the system is powered off.

    shutdown_enabled gates the power-off itself and defaults to false: alarms
    are always logged, but the system is only shut down when the platform JSON
    opts in. Leave it false until leak scores have been trusted on hardware.
    """

    JSON_FIELD_WAIT_INTERVAL = 'wait_interval'
    JSON_FIELD_SHUTDOWN_ENABLED = 'shutdown_enabled'

    def __init__(self):
        self.wait_interval = LEAK_SHUTDOWN_WAIT_INTERVAL
        self.shutdown_enabled = False
        self._critical_since = {}
        self._alarmed = set()

    def load_from_json(self, json_obj):
        if self.JSON_FIELD_WAIT_INTERVAL in json_obj:
            self.wait_interval = int(json_obj[self.JSON_FIELD_WAIT_INTERVAL])
        if self.JSON_FIELD_SHUTDOWN_ENABLED in json_obj:
            self.shutdown_enabled = str(
                json_obj[self.JSON_FIELD_SHUTDOWN_ENABLED]).strip().lower() == 'true'

    def execute(self, thermal_info_dict):
        info = thermal_info_dict.get(LeakInfo.INFO_NAME)
        if not isinstance(info, LeakInfo):
            return

        leaking = dict((s.get_name(), (s, score)) for s, score in info.get_leaking_sensors())

        for name in list(self._alarmed):
            if name not in leaking:
                self._alarmed.discard(name)
                self._critical_since.pop(name, None)
                sonic_logger.log_notice(f"[LEAK] Cleared: {name} no longer reporting a leak")

        now = time.time()
        for name, (sensor, score) in leaking.items():
            rat = sensor.get_high_threshold()
            ft = sensor.get_high_critical_threshold()

            if name not in self._alarmed:
                self._alarmed.add(name)
                sonic_logger.log_error(
                    f"[LEAK] Leak detected on {name}: score {score} "
                    f"(red alarm {rat}, shutdown {ft})")

            if ft is None or score < ft:
                self._critical_since.pop(name, None)
                if rat is not None and score >= rat:
                    sonic_logger.log_error(
                        f"[LEAK] {name} at red alarm level: score {score} >= {rat}")
                continue

            started = self._critical_since.setdefault(name, now)
            elapsed = now - started
            if elapsed < self.wait_interval:
                sonic_logger.log_error(
                    f"[LEAK] {name} at shutdown level: score {score} >= {ft}, "
                    f"sustained {int(elapsed)}s of {self.wait_interval}s")
                continue

            reason = (f"liquid cooling leak on {name} (score {score} >= shutdown "
                      f"threshold {ft} sustained {int(elapsed)}s)")
            if not self.shutdown_enabled:
                sonic_logger.log_error(
                    f"[LEAK] shutdown suppressed (shutdown_enabled=false): {reason}")
                continue

            self._request_shutdown(reason)
            return

    @staticmethod
    def _request_shutdown(reason):
        """Write shutdown cause and trigger system shutdown."""
        cmd = (f'echo "shutdown requested by docker-platform-monitor due to '
               f'{reason}" > /host/reboot-cause/shutdown_request')
        sonic_logger.log_error(f"[LEAK] Requesting shutdown: {reason}")
        try:
            subprocess.run(cmd, shell=True, check=True, executable="/bin/bash")
            sonic_logger.log_warning("Shutdown request written successfully.")
        except subprocess.CalledProcessError as e:
            sonic_logger.log_warning(f"Shutdown failed: {e}")
