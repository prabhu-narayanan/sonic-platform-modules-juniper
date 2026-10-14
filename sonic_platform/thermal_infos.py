try:
    from sonic_platform_base.sonic_thermal_control.thermal_info_base import ThermalPolicyInfoBase
    from sonic_platform_base.sonic_thermal_control.thermal_json_object import thermal_json_object
    from sonic_py_common import logger
except ImportError as e:
    raise ImportError(str(e) + ' - required module not found') from e

import random
import time
import os

sonic_logger = logger.Logger('thermal_info')
sonic_logger.set_min_log_priority_warning()

# ─────────────────────────────────────────────────────────────────────────────
# Temperature simulation for EM Policy testing.
#
# When enabled, a fixed offset (positive or negative) is added to real sensor
# readings to simulate heating/cooling and trigger fan speed changes via the
# EM policy algorithm. Simulated temps are clamped to 0°C minimum.
#
# Usage (positive → heat up → increase fan speed):
#   echo 12 > /tmp/thermal_sim_offset   → adds 12°C (triggers ~50% fan)
#   echo 16 > /tmp/thermal_sim_offset   → adds 16°C (triggers ~70% fan)
#   echo 22 > /tmp/thermal_sim_offset   → adds 22°C (triggers 100% fan)
#   echo 30 > /tmp/thermal_sim_offset   → adds 30°C (triggers minor alarm + 100%)
#
# Usage (negative → cool down → decrease fan speed):
#   echo -- -10 > /tmp/thermal_sim_offset  → subtracts 10°C
#   echo -- -20 > /tmp/thermal_sim_offset  → subtracts 20°C
#   echo -- -30 > /tmp/thermal_sim_offset  → subtracts 30°C (most sensors below WT → ~40%)
#
# Disable:
#   echo 0  > /tmp/thermal_sim_offset   → disables (real temps only)
#   rm /tmp/thermal_sim_offset           → disables simulation
#
# Fan speed formula: speed = 40 + (100-40) * ratio
#   where ratio = (temp - WT) / (HIGH_THRESHOLD - WT)
#
# Most sensitive sensor: MB Left Front (real ~29°C, WT=39, HIGH=51, YAT=60)
#   offset=10 → temp=39 → ratio=0   → fan=40%
#   offset=12 → temp=41 → ratio=0.17→ fan=50%
#   offset=14 → temp=43 → ratio=0.33→ fan=60%
#   offset=16 → temp=45 → ratio=0.5 → fan=70%
#   offset=18 → temp=47 → ratio=0.67→ fan=80%
#   offset=20 → temp=49 → ratio=0.83→ fan=90%
#   offset=22 → temp=51 → ratio=1.0 → fan=100%
#   offset=31 → temp=60 → YAT alarm → fan=100% (minor)
#   offset=36 → temp=65 → RAT alarm → fan=100% (major → shutdown)
#   offset=41 → temp=70 → FIRE      → immediate shutdown
#
# QFX5250 (baseline ~85% due to hot RVDD sensors):
#   offset=-20 → cools all sensors below WT → fan=40%
#   offset=-15 → fan≈50%
#   offset=-10 → fan≈60%
#   offset=0   → fan≈85% (real temps)
#   offset=+10 → fan≈93%
#   offset=+20 → fan=100%
# ─────────────────────────────────────────────────────────────────────────────

_SIM_OFFSET_FILE = "/tmp/thermal_sim_offset"


def _get_sim_offset():
    """
    Read temperature offset from /tmp/thermal_sim_offset.
    Supports positive (heat) and negative (cool) offsets.
    Returns 0.0 if file doesn't exist or contains 0.
    """
    if not os.path.exists(_SIM_OFFSET_FILE):
        return 0.0
    try:
        with open(_SIM_OFFSET_FILE, 'r') as f:
            val = float(f.read().strip())
        return val if val != 0 else 0.0
    except (IOError, ValueError):
        return 0.0


@thermal_json_object('fan_info')
class FanInfo(ThermalPolicyInfoBase):
    """
    Fan information needed by thermal policy
    """
    # Fan information name
    INFO_NAME = 'fan_info'

    def __init__(self):
        self._absence_fans = set()
        self._presence_fans = set()
        self._good_fans = set()
        self._bad_fans = set()
        self._status_changed = False

    def collect(self, chassis):
        """
        Collect absence and presence fans.
        :param chassis: The chassis object
        :return:
        """
        self._status_changed = False

        for fandrawer in chassis.get_all_fan_drawers():
            # Drawer is "present" if ANY fan in it reports present
            any_present = any(fan.get_presence() for fan in fandrawer.get_all_fans())
            if any_present and fandrawer not in self._presence_fans:
                self._presence_fans.add(fandrawer)
                self._status_changed = True
                self._absence_fans.discard(fandrawer)
            elif not any_present and fandrawer not in self._absence_fans:
                self._absence_fans.add(fandrawer)
                self._status_changed = True
                self._presence_fans.discard(fandrawer)

        for fandrawer in chassis.get_all_fan_drawers():
            for fan in fandrawer.get_all_fans():
                if fan.get_presence():
                    current_rpm = fan.get_speed_rpm()
                    max_rpm = fan.get_max_rpm()
                    # 0 RPM on a present fan = stuck/faulty
                    is_good = current_rpm > 0  # over-speed is not a fault

                    if is_good and fan not in self._good_fans:
                        self._good_fans.add(fan)
                        self._status_changed = True
                        self._bad_fans.discard(fan)
                    elif not is_good and fan not in self._bad_fans:
                        self._bad_fans.add(fan)
                        self._status_changed = True
                        self._good_fans.discard(fan)

    def get_absence_fans(self):
        """
        Retrieves absence fans
        :return: A set of absence fans
        """
        return self._absence_fans

    def get_presence_fans(self):
        """
        Retrieves presence fans
        :return: A set of presence fans
        """
        return self._presence_fans

    def get_good_fans(self):
        """
        Retrieves good fans
        :return: A set of good fans
        """
        return self._good_fans

    def get_bad_fans(self):
        """
        Retrieves bad fans
        :return: A set of bad fans
        """
        return self._bad_fans

    def is_status_changed(self):
        """
        Retrieves if the status of fan information changed
        :return: True if status changed else False
        """
        return self._status_changed

@thermal_json_object('thermal_info')
class ThermalInfo(ThermalPolicyInfoBase):
    """
    Thermal information needed by thermal policy
    """
    # Fan information name
    INFO_NAME = 'thermal_info'

    def __init__(self):
        """Initialize ThermalInfo with default values.

        Attributes:
            temp_raise_ratio (list): List of temperature raise ratios.
            temp_fall_ratio (list): List of temperature fall ratios.
            current_temp_ratio (list): List of current temperature ratios,
                initialized to 0.0 with size 200. Changed from 80 to 200 to
                accommodate platforms with a higher number of thermal sensors,
                preventing index out of range errors on systems with more than
                80 thermal entries.
            temp_alarms (list): List of temperature alarms.
            temp_sensor_names (list): List of temperature sensor names.
            _over_high_critical_threshold (bool): Flag indicating if temperature
                is over the high critical threshold.
            _set_fan_ctl_speed (bool): Flag indicating if fan control speed is set.
            fanctl_speed (int): Current fan control speed.
            min_speed (int): Minimum fan speed (default 40).
            max_speed (int): Maximum fan speed (default 100).
            num_of_thermals (int): Number of thermal sensors.
        """
        self.temp_raise_ratio = []
        self.temp_fall_ratio = []
        # Initialize to -1.0 (below zero = below WT = min fan speed).
        # Using 0.0 would bias the first cycle to 40+60*0=40% even when
        # sensors haven't been read yet, and would prevent the hysteresis
        # from ever falling below 0 once a sensor ratio was computed.
        self.current_temp_ratio = [-1.0] * 200
        self.temp_alarms = []
        self.temp_sensor_names = []
        self._over_high_critical_threshold = False
        self._set_fan_ctl_speed = False
        self.fanctl_speed = 0
        self.min_speed = 40
        self.max_speed = 100
        self.num_of_thermals = 0

    def collect(self, chassis):
        """
        Collect thermal sensor temperature change status
        :param chassis: The chassis object
        :return:
        """
        self._over_high_critical_threshold = False
        self._set_fan_ctl_speed = False

        # Read min/max fan speed from THERMAL_CTRL in pddf-device.json
        thermal_ctrl = {}
        if hasattr(chassis, 'pddf_obj') and hasattr(chassis.pddf_obj, 'data'):
            thermal_ctrl = chassis.pddf_obj.data.get(
                'THERMAL_CTRL', {}).get('dev_attr', {})
        self.min_speed = int(thermal_ctrl.get('min_fan_speed', '40'))
        self.max_speed = int(thermal_ctrl.get('max_fan_speed', '100'))
        self.max_temp_ratio = -10.0
        if hasattr(chassis, 'get_thermal_policy_thermals'):
            thermals = chassis.get_thermal_policy_thermals()
        else:
            thermals = [chassis.get_thermal(index)
                        for index in range(chassis.get_num_thermals())]
        self.num_of_thermals = len(thermals)
        # Ensure current_temp_ratio list is large enough to hold all thermal sensors.
        # This is a safeguard against index out of range errors on platforms with more than 80 thermal sensors. The list is initialized to 0.0 for all entries.
        if len(self.current_temp_ratio) < self.num_of_thermals:
            self.current_temp_ratio.extend([0.0] * (self.num_of_thermals - len(self.current_temp_ratio)))
        self.temp_raise_ratio = [0.0] * self.num_of_thermals
        self.temp_fall_ratio = [0.0] * self.num_of_thermals
        self.temp_alarms = ["normal"] * self.num_of_thermals
        self.temp_sensor_names = ["sensor"] * self.num_of_thermals

        # Previously, each thermal was fetched and read separately in the
        # alarm loop and ratio loop — that's 2 sysfs reads per sensor.
        # With 15 sensors, this saves 15 sysfs reads per 15s cycle.
        # Determine if any fans are bad (used for threshold selection)
        fan_info = None
        has_bad_fans = False
        try:
            from .thermal_infos import FanInfo
            if hasattr(chassis, '_thermal_manager'):
                fan_info_dict = getattr(chassis._thermal_manager, '_thermal_info_dict', {})
                if FanInfo.INFO_NAME in fan_info_dict:
                    fan_info = fan_info_dict[FanInfo.INFO_NAME]
                    has_bad_fans = len(fan_info.get_bad_fans()) > 0
        except Exception:
            pass
        self._has_bad_fans = has_bad_fans

        temps = [None] * self.num_of_thermals
        sim_offset = _get_sim_offset()
        for index, thermal in enumerate(thermals):
            self.temp_sensor_names[index] = thermal.get_name()
            real_temp = thermal.get_temperature()
            if real_temp is not None and sim_offset != 0:
                temps[index] = max(0.0, real_temp + sim_offset)
                sonic_logger.log_warning(
                    f"Thermal {thermal.get_name()} SIMULATED: real={real_temp:.1f}°C "
                    f"+ offset={sim_offset:.1f}°C → {temps[index]:.1f}°C")
            else:
                temps[index] = real_temp
                sonic_logger.log_info(f"Thermal {thermal.get_name()} current temperature: {temps[index]}°C")

        # --- Alarm classification (uses cached temps) ---
        # Use bad_fan thresholds when any fan is degraded
        for index, thermal in enumerate(thermals):
            temp_current = temps[index]
            thermal_FT = thermal.get_FT()

            if has_bad_fans:
                thermal_YAT = thermal.get_YATBF() or thermal.get_YAT()
                thermal_RAT = thermal.get_RATBF() or thermal.get_RAT()
            else:
                thermal_YAT = thermal.get_YAT()
                thermal_RAT = thermal.get_RAT()

            # Skip sensor if temperature or thresholds are unavailable
            if None in (temp_current, thermal_YAT, thermal_RAT, thermal_FT):
                continue

            if temp_current >= thermal_FT:
                self.temp_alarms[index] = "fire"
                self._over_high_critical_threshold = True
            elif temp_current >= thermal_RAT:
                self.temp_alarms[index] = "major"
            elif temp_current >= thermal_YAT:
                self.temp_alarms[index] = "minor"
            else:
                self.temp_alarms[index] = "normal"

        # --- Ratio computation (reuses cached temps — no second sysfs read) ---
        # Track which sensors have valid EM thresholds (WTC/WT/HIGH).
        # Sensors without these (e.g. SFP port thermals) must be excluded
        # from the hysteresis loop to avoid their stale current_temp_ratio=0.0
        # inflating max_temp_ratio and preventing fan speed from dropping.
        valid_ratio_sensors = set()
        for index, thermal in enumerate(thermals):
            current_temp = temps[index]
            thermal_WTC = thermal.get_WTC()
            low_limit = thermal.get_WT()
            if has_bad_fans:
                high_limit = thermal.get_high_threshold_bad_fan() or thermal.get_high_threshold()
            else:
                high_limit = thermal.get_high_threshold()

            # Skip sensor if temperature or thresholds are unavailable
            if None in (current_temp, thermal_WTC, low_limit, high_limit):
                continue

            valid_ratio_sensors.add(index)

            delta = low_limit - thermal_WTC
            if low_limit < high_limit:
                raise_ratio = (current_temp - low_limit)/(high_limit - low_limit)
                self.temp_raise_ratio[index] = raise_ratio
            elif low_limit > high_limit:
                raise_ratio = (current_temp - high_limit)/(low_limit - high_limit)
                self.temp_raise_ratio[index] = raise_ratio
            else:
                if current_temp > high_limit:
                    raise_ratio = 1
                elif current_temp < high_limit:
                    raise_ratio = -1
                else:
                    raise_ratio = 0
                self.temp_raise_ratio[index] = raise_ratio

            fall_low_limit = thermal_WTC
            fall_high_limit = high_limit - delta

            if fall_low_limit < fall_high_limit:
                fall_ratio = (current_temp - fall_low_limit)/(fall_high_limit - fall_low_limit)
                self.temp_fall_ratio[index] = fall_ratio
            elif fall_low_limit > fall_high_limit: 
                fall_ratio = (current_temp - fall_high_limit)/(fall_low_limit - fall_high_limit)
                self.temp_fall_ratio[index] = fall_ratio
            else:
                if current_temp > fall_high_limit:
                    fall_ratio = 1
                elif current_temp < fall_high_limit:
                    fall_ratio = -1
                else:
                    fall_ratio = 0 
                self.temp_fall_ratio[index] = fall_ratio

        # --- Hysteresis: only consider sensors with valid EM thresholds ---
        for index in range(self.num_of_thermals):
            if index not in valid_ratio_sensors:
                continue
            if self.current_temp_ratio[index] > self.temp_fall_ratio[index]:
                self.current_temp_ratio[index] = self.temp_fall_ratio[index]
                self.max_temp_ratio = max(self.current_temp_ratio[index],self.max_temp_ratio)
            elif self.current_temp_ratio[index] < self.temp_raise_ratio[index]:
                self.current_temp_ratio[index] = self.temp_raise_ratio[index]
                self.max_temp_ratio = max(self.current_temp_ratio[index],self.max_temp_ratio)
            else:
                self.max_temp_ratio = max(self.current_temp_ratio[index],self.max_temp_ratio)

        if self.max_temp_ratio > 1:
            self.max_temp_ratio = 1
        elif self.max_temp_ratio < 0:
            self.max_temp_ratio = 0

        self.fanctl_speed = round(self.min_speed + ((self.max_speed - self.min_speed) * self.max_temp_ratio))
        sonic_logger.log_warning(
            f"EM-Debug: max_ratio={self.max_temp_ratio:.4f} "
            f"valid={len(valid_ratio_sensors)}/{self.num_of_thermals} "
            f"fanctl={self.fanctl_speed}% min={self.min_speed} max={self.max_speed}")
        self._set_fan_ctl_speed = True

    def is_over_high_critical_threshold(self):
        """
        Retrieves if the temperature is over high critical threshold
        :return: True if the temperature is over high critical threshold else False
        """
        return self._over_high_critical_threshold

    def is_set_fan_ctl_speed(self):
        """
        Retrieves if the temperature is warm up and over high threshold
        :return: True if the temperature is warm up and over high threshold else False
        """
        return self._set_fan_ctl_speed

    def get_fanctl_speed(self):
        if (self.fanctl_speed >= self.min_speed and self.fanctl_speed <= self.max_speed):
            return self.fanctl_speed
        else:
            return 0
    
    def get_temp_sensor_alarms(self):
        return self.temp_alarms 
    
    def get_num_sensors(self):
        return self.num_of_thermals

    def get_sensor_name(self, index):
        return self.temp_sensor_names[index]
        

@thermal_json_object('psu_info')
class PsuInfo(ThermalPolicyInfoBase):
    """
    PSU information needed by thermal policy
    """
    INFO_NAME = 'psu_info'

    def __init__(self):
        self._absence_psus = set()
        self._presence_psus = set()
        self._status_changed = False

    def collect(self, chassis):
        """
        Collect absence and presence PSUs.
        :param chassis: The chassis object
        :return:
        """
        self._status_changed = False
        for psu in chassis.get_all_psus():
            if psu.get_presence() and psu.get_powergood_status() and psu not in self._presence_psus:
                self._presence_psus.add(psu)
                self._status_changed = True
                if psu in self._absence_psus:
                    self._absence_psus.remove(psu)
            elif (not psu.get_presence() or not psu.get_powergood_status()) and psu not in self._absence_psus:
                self._absence_psus.add(psu)
                self._status_changed = True
                if psu in self._presence_psus:
                    self._presence_psus.remove(psu)

    def get_absence_psus(self):
        """
        Retrieves presence PSUs
        :return: A set of absence PSUs
        """
        return self._absence_psus

    def get_presence_psus(self):
        """
        Retrieves presence PSUs
        :return: A set of presence fans
        """
        return self._presence_psus

    def is_status_changed(self):
        """
        Retrieves if the status of PSU information changed
        :return: True if status changed else False
        """
        return self._status_changed

@thermal_json_object('chassis_info')
class ChassisInfo(ThermalPolicyInfoBase):
    """
    Chassis information needed by thermal policy
    """
    INFO_NAME = 'chassis_info'

    def __init__(self):
        self._chassis = None

    def collect(self, chassis):
        """
        Collect platform chassis.
        :param chassis: The chassis object
        :return:
        """
        self._chassis = chassis

    def get_chassis(self):
        """
        Retrieves platform chassis object
        :return: A platform chassis object.
        """
        return self._chassis
