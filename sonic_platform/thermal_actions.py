try:
    from sonic_platform_base.sonic_thermal_control.thermal_action_base import ThermalPolicyActionBase
    from sonic_platform_base.sonic_thermal_control.thermal_json_object import thermal_json_object
    from sonic_py_common import logger
    import time
    import os
    import subprocess
except ImportError as e:
    raise ImportError(str(e) + ' - required module not found') from e

sonic_logger = logger.Logger('thermal_actions')
sonic_logger.set_min_log_priority_warning()

class SetFanSpeedAction(ThermalPolicyActionBase):
    """
    Base thermal action class to set speed for fans
    """
    # JSON field definition
    JSON_FIELD_SPEED = 'speed'
    JSON_FIELD_DEFAULT_SPEED = 'default_speed'
    JSON_FIELD_HIGHTEMP_SPEED = 'hightemp_speed'
    JSON_FIELD_WAIT_INTERVAL = 'wait_interval'
    def __init__(self):
        """
        Constructor of SetFanSpeedAction
        """
        self.default_speed = 60
        self.hightemp_speed = 100
        self.wait_interval = 240
        self.speed = self.default_speed

    def load_from_json(self, json_obj):
        """
        Construct SetFanSpeedAction via JSON. JSON example:
            {
                "type": "fan.all.set_speed"
                "speed": "100"
            }
        :param json_obj: A JSON object representing a SetFanSpeedAction action.
        :return:
        """
        if SetFanSpeedAction.JSON_FIELD_SPEED in json_obj:
            speed = float(json_obj[SetFanSpeedAction.JSON_FIELD_SPEED])
            if speed < 0 or speed > 100:
                raise ValueError('SetFanSpeedAction invalid speed value {} in JSON policy file, valid value should be [0, 100]'.
                                 format(speed))
            self.speed = float(json_obj[SetFanSpeedAction.JSON_FIELD_SPEED])
        else:
            raise ValueError('SetFanSpeedAction missing mandatory field {} in JSON policy file'.
                             format(SetFanSpeedAction.JSON_FIELD_SPEED))

    @classmethod
    def set_all_fan_speed(cls, thermal_info_dict, speed):
        from .thermal_infos import FanInfo
        if FanInfo.INFO_NAME in thermal_info_dict and isinstance(thermal_info_dict[FanInfo.INFO_NAME], FanInfo):
            fan_info_obj = thermal_info_dict[FanInfo.INFO_NAME]
            for fandrawer in fan_info_obj.get_presence_fans():
                for fan in fandrawer.get_all_fans():
                    fan.set_speed(int(speed))

@thermal_json_object('fan.all.set_speed')
class SetAllFanSpeedAction(SetFanSpeedAction):
    """
    Action to set speed for all fans
    """
    def execute(self, thermal_info_dict):
        """
        Set speed for all fans
        :param thermal_info_dict: A dictionary stores all thermal information.
        :return:
        """
        SetAllFanSpeedAction.set_all_fan_speed(thermal_info_dict, self.speed)

@thermal_json_object('thermal.temp_check_and_set_all_fan_speed')
class ThermalRecoverAction(SetFanSpeedAction):
    """
    Action to check thermal sensor temperature change status and set speed for all fans
    """ 
    prev_speed = 0

    def load_from_json(self, json_obj):
        """
        Construct ThermalRecoverAction via JSON. JSON example:
            {
                "type": "thermal.temp_check_and_set_all_fan_speed"
                "default_speed": "25",
                "threshold1_speed": "40",
                "threshold2_speed": "75",
                "hightemp_speed": "100",
                "wait_interval": "240"
            }
        :param json_obj: A JSON object representing a ThermalRecoverAction action.
        :return:
        """
        if SetFanSpeedAction.JSON_FIELD_DEFAULT_SPEED in json_obj:
            default_speed = float(json_obj[SetFanSpeedAction.JSON_FIELD_DEFAULT_SPEED])
            if default_speed < 0 or default_speed > 100:
                raise ValueError('SetFanSpeedAction invalid default speed value {} in JSON policy file, valid value should be [0, 100]'.
                                 format(default_speed))
            self.default_speed = float(json_obj[SetFanSpeedAction.JSON_FIELD_DEFAULT_SPEED])
        else:
            raise ValueError('SetFanSpeedAction missing mandatory field {} in JSON policy file'.
                             format(SetFanSpeedAction.JSON_FIELD_DEFAULT_SPEED))

        if SetFanSpeedAction.JSON_FIELD_HIGHTEMP_SPEED in json_obj:
            hightemp_speed = float(json_obj[SetFanSpeedAction.JSON_FIELD_HIGHTEMP_SPEED])
            if hightemp_speed < 0 or hightemp_speed > 100:
                raise ValueError('SetFanSpeedAction invalid hightemp speed value {} in JSON policy file, valid value should be [0, 100]'.
                                 format(hightemp_speed))
            self.hightemp_speed = float(json_obj[SetFanSpeedAction.JSON_FIELD_HIGHTEMP_SPEED])
        else:
            raise ValueError('SetFanSpeedAction missing mandatory field {} in JSON policy file'.
                             format(SetFanSpeedAction.JSON_FIELD_HIGHTEMP_SPEED))

        sonic_logger.log_warning("ThermalRecoverAction: default: {}, hightemp: {}".format(self.default_speed, self.hightemp_speed))
        if SetFanSpeedAction.JSON_FIELD_WAIT_INTERVAL in json_obj:
            self.wait_interval = int(json_obj[SetFanSpeedAction.JSON_FIELD_WAIT_INTERVAL])
        else:
            raise ValueError('SetFanSpeedAction missing mandatory field {} in JSON policy file'.
                             format(SetFanSpeedAction.JSON_FIELD_HIGHTEMP_SPEED))


    def execute(self, thermal_info_dict):
        """
        Check check thermal sensor temperature change status and set speed for all fans
        :param thermal_info_dict: A dictionary stores all thermal information.
        :return:
        """
        from .thermal_infos import ThermalInfo
        if ThermalInfo.INFO_NAME in thermal_info_dict and \
            isinstance(thermal_info_dict[ThermalInfo.INFO_NAME], ThermalInfo):

            thermal_info_obj = thermal_info_dict[ThermalInfo.INFO_NAME]
            temp_sensor_alarms = thermal_info_obj.get_temp_sensor_alarms()
            num_of_thermals = thermal_info_obj.get_num_sensors()
            fire_alarm = 0
            major_alarm = 0
            minor_alarm = 0

            for index in range(num_of_thermals):   
                if temp_sensor_alarms[index] == "fire":
                    fire_alarm = fire_alarm + 1
                    sonic_logger.log_warning(f"Sensor: {thermal_info_obj.get_sensor_name(index)} is having temperature greater than fire threshold(fire alarm)")
                elif temp_sensor_alarms[index] == "major":
                    major_alarm = major_alarm + 1
                    sonic_logger.log_warning(f"Sensor: {thermal_info_obj.get_sensor_name(index)} is having temperature greater than red threshold(major alarm)")
                    if major_alarm < 2:
                        ThermalRecoverAction.set_all_fan_speed(thermal_info_dict, self.hightemp_speed)
                elif temp_sensor_alarms[index] == "minor":
                    minor_alarm = minor_alarm + 1
                    sonic_logger.log_warning(f"Sensor: {thermal_info_obj.get_sensor_name(index)} is having temperature greater than yellow threshold(minor alarm)")
                    if minor_alarm < 2:
                        ThermalRecoverAction.set_all_fan_speed(thermal_info_dict, self.hightemp_speed)
            
            if major_alarm > 0:
                sonic_logger.log_warning(f"SHUTTING DOWN THE DEVICE in {self.wait_interval} sec")
                time.sleep(self.wait_interval)
                cmd = 'echo "shutdown requested by docker-platform-monitor due to Red Alarm for temp sensor is detected" > /host/reboot-cause/shutdown_request'
                try:
                    subprocess.run(cmd, shell=True, check=True, executable="/bin/bash")
                    sonic_logger.log_warning("Shutdown request written successfully.")
                except subprocess.CalledProcessError as e:
                    sonic_logger.log_warning(f"Shutdown failed: {e}")

            if fire_alarm > 0:
                sonic_logger.log_warning(f"SHUTTING DOWN THE DEVICE in {self.wait_interval} sec")
                time.sleep(3)
                cmd = 'echo "shutdown requested by docker-platform-monitor due to FIRE alarm for temp sensor is detected" > /host/reboot-cause/shutdown_request'
                try:
                    subprocess.run(cmd, shell=True, check=True, executable="/bin/bash")
                    sonic_logger.log_warning("Shutdown request written successfully.")
                except subprocess.CalledProcessError as e:
                    sonic_logger.log_warning(f"Shutdown failed: {e}")

            if not fire_alarm and not major_alarm and not minor_alarm:
                fanctl_speed = thermal_info_obj.get_fanctl_speed()
                if fanctl_speed != 0:
                    if ThermalRecoverAction.prev_speed != fanctl_speed:
                        sonic_logger.log_warning(f"Changing fan speed to {fanctl_speed} as per EM-Policy Algo")
                else:
                    sonic_logger.log_warning(f"Wrong fanctl_speed, use default fan speed {self.default_speed}")
                    fanctl_speed = self.default_speed
                ThermalRecoverAction.prev_speed = fanctl_speed
                ThermalRecoverAction.set_all_fan_speed(thermal_info_dict, fanctl_speed)

@thermal_json_object('thermal.shutdown_check')
class ThermalShutdownAction(ThermalPolicyActionBase):
    """
    Shutdown-only thermal action for fan-less / liquid-cooled systems.
    Monitors thermal sensors and triggers shutdown on RAT or FT without
    any fan speed manipulation. Use this in thermal_policy.json for
    platforms where ThermalManager has no fan control (e.g. liquid-cool).

    JSON example:
        {
            "type": "thermal.shutdown_check",
            "wait_interval": "240"
        }
    """
    JSON_FIELD_WAIT_INTERVAL = 'wait_interval'

    def __init__(self):
        self.wait_interval = 240

    def load_from_json(self, json_obj):
        if self.JSON_FIELD_WAIT_INTERVAL in json_obj:
            self.wait_interval = int(json_obj[self.JSON_FIELD_WAIT_INTERVAL])

    def execute(self, thermal_info_dict):
        """
        Check thermal sensor alarms and trigger shutdown if RAT or FT exceeded.
        No fan speed control — suitable for liquid-cooled systems.

        SFP/optic sensors (et-0/0/X) that exceed fire or major thresholds
        are powered off individually — the device is NOT shut down for optic
        over-temperature.  Only non-optic (system) sensors trigger a full
        device shutdown.
        """
        from .thermal_infos import ThermalInfo
        if ThermalInfo.INFO_NAME not in thermal_info_dict or \
                not isinstance(thermal_info_dict[ThermalInfo.INFO_NAME], ThermalInfo):
            return

        thermal_info_obj = thermal_info_dict[ThermalInfo.INFO_NAME]
        temp_sensor_alarms = thermal_info_obj.get_temp_sensor_alarms()
        num_of_thermals = thermal_info_obj.get_num_sensors()

        system_fire = 0
        system_major = 0
        sfp_fire_ports = []
        sfp_major_ports = []

        # Classify alarms into SFP vs system sensors
        # Access the chassis thermal list to check is_sfp_thermal attribute
        from .thermal_infos import ChassisInfo
        chassis = None
        if ChassisInfo.INFO_NAME in thermal_info_dict:
            chassis_info = thermal_info_dict[ChassisInfo.INFO_NAME]
            chassis = chassis_info.get_chassis()

        for index in range(num_of_thermals):
            alarm = temp_sensor_alarms[index]
            if alarm not in ("fire", "major"):
                continue

            sensor_name = thermal_info_obj.get_sensor_name(index)
            is_sfp = False
            sfp_port_index = -1

            # Check if this sensor is an SFP thermal
            if chassis:
                try:
                    if hasattr(chassis, 'get_thermal_policy_thermals'):
                        thermal_obj = chassis.get_thermal_policy_thermals()[index]
                    else:
                        thermal_obj = chassis.get_thermal(index)
                    if getattr(thermal_obj, 'is_sfp_thermal', False):
                        is_sfp = True
                        sfp_port_index = getattr(thermal_obj, '_port_index', -1)
                except Exception:
                    pass

            if is_sfp:
                if alarm == "fire":
                    sfp_fire_ports.append((sfp_port_index, sensor_name))
                    sonic_logger.log_warning(
                        f"[LIQUID-COOL] Optic {sensor_name} (port {sfp_port_index}) "
                        f"exceeded FIRE threshold — will power off optic")
                elif alarm == "major":
                    sfp_major_ports.append((sfp_port_index, sensor_name))
                    sonic_logger.log_warning(
                        f"[LIQUID-COOL] Optic {sensor_name} (port {sfp_port_index}) "
                        f"exceeded RED alarm threshold — will power off optic")
            else:
                if alarm == "fire":
                    system_fire += 1
                    sonic_logger.log_warning(
                        f"[LIQUID-COOL] Sensor: {sensor_name} "
                        f"exceeded FIRE threshold")
                elif alarm == "major":
                    system_major += 1
                    sonic_logger.log_warning(
                        f"[LIQUID-COOL] Sensor: {sensor_name} "
                        f"exceeded RED alarm threshold")

        # --- Handle overheating optics: power off individually ---
        if chassis and (sfp_fire_ports or sfp_major_ports):
            all_hot_ports = sfp_fire_ports + sfp_major_ports
            for port_index, sensor_name in all_hot_ports:
                self._shutdown_optic(chassis, port_index, sensor_name)

        # --- Handle system sensor alarms: full device shutdown ---

        # Fire alarm — emergency shutdown (3 sec)
        if system_fire > 0:
            sonic_logger.log_warning(
                "[LIQUID-COOL] SYSTEM FIRE ALARM: SHUTTING DOWN DEVICE in 3 sec")
            time.sleep(3)
            self._request_shutdown(
                "FIRE alarm for temp sensor is detected (liquid-cool system)")
            return

        # Major alarm (RAT) — graceful shutdown after wait_interval
        if system_major > 0:
            sonic_logger.log_warning(
                f"[LIQUID-COOL] SYSTEM RED ALARM: SHUTTING DOWN DEVICE in "
                f"{self.wait_interval} sec")
            time.sleep(self.wait_interval)
            self._request_shutdown(
                "Red Alarm for temp sensor is detected (liquid-cool system)")

    @staticmethod
    def _shutdown_optic(chassis, port_index, sensor_name):
        """Power off an individual optic that exceeded thermal threshold."""
        try:
            sfp = chassis.get_sfp(port_index)
            if sfp is None:
                sonic_logger.log_warning(
                    f"[LIQUID-COOL] Cannot get SFP object for port {port_index}")
                return

            # Put module in reset (deactivates data path)
            if hasattr(sfp, 'reset_in'):
                sfp.reset_in()
                sonic_logger.log_warning(
                    f"[LIQUID-COOL] Optic {sensor_name} (port {port_index}) "
                    f"put in reset state")

            # Power off hotswap (cuts power to the module)
            if hasattr(sfp, 'set_hotswap_en'):
                sfp.set_hotswap_en(False)
                sonic_logger.log_warning(
                    f"[LIQUID-COOL] Optic {sensor_name} (port {port_index}) "
                    f"power disabled (hotswap off)")
            else:
                sonic_logger.log_warning(
                    f"[LIQUID-COOL] Optic {sensor_name} (port {port_index}) "
                    f"no hotswap control available — reset only")
        except Exception as e:
            sonic_logger.log_warning(
                f"[LIQUID-COOL] Failed to shutdown optic {sensor_name} "
                f"(port {port_index}): {e}")

    def _request_shutdown(self, reason):
        """Write shutdown cause and trigger system shutdown."""
        cmd = (f'echo "shutdown requested by docker-platform-monitor due to '
               f'{reason}" > /host/reboot-cause/shutdown_request')
        try:
            subprocess.run(cmd, shell=True, check=True, executable="/bin/bash")
            sonic_logger.log_warning("Shutdown request written successfully.")
        except subprocess.CalledProcessError as e:
            sonic_logger.log_warning(f"Shutdown failed: {e}")


@thermal_json_object('switch.shutdown')
class SwitchPolicyAction(ThermalPolicyActionBase):
    """
    Base class for thermal action. Once all thermal conditions in a thermal policy are matched,
    all predefined thermal action will be executed.
    """
    def execute(self, thermal_info_dict):
        """
        Take action when thermal condition matches. For example, adjust speed of fan or shut
        down the switch.
        :param thermal_info_dict: A dictionary stores all thermal information.
        :return:
        """
        sonic_logger.log_warning("More than one fan is not detected/ more than 3 bad fans are present, wait for 30sec and reboot Device")
        time.sleep(30)
        cmd = 'echo "shutdown requested by docker-platform-monitor due to more than 1 fantray is missing or more than 3 bad fans are present" > /host/reboot-cause/shutdown_request'

        # Run command in shell safely
        try:
            subprocess.run(cmd, shell=True, check=True, executable="/bin/bash")
            sonic_logger.log_warning("Shutdown request written successfully.")
        except subprocess.CalledProcessError as e:
            sonic_logger.log_warning(f"Shutdown failed: {e}")

