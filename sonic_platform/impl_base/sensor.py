#!/usr/bin/env python3
#
# impl_base/sensor.py — default VoltageSensor implementation for sensor.py.
#
# Copyright (c) 2026, Juniper Networks, Inc.
# All rights reserved.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# SensorImplBase owns the hwmon-backed voltage-sensor behavior and state
# (sensor_index, VOLTAGE_SENSORS table). self._host is the owning VoltageSensor
# facade (a VoltageSensorBase).

import os
import subprocess
import glob
import syslog

SYSLOG_IDENTIFIER = "Voltage-Sensor"


def log_err(msg):
    syslog.openlog(SYSLOG_IDENTIFIER)
    syslog.syslog(syslog.LOG_ERR, msg)
    syslog.closelog()


def log_info(msg):
    syslog.openlog(SYSLOG_IDENTIFIER)
    syslog.syslog(syslog.LOG_INFO, msg)
    syslog.closelog()


class SensorImplBase:
    """Default hwmon voltage-sensor public API. State (sensor_index,
    VOLTAGE_SENSORS table) lives on the facade (self._host)."""

    def __init__(self, host):
        self._host = host

    def get_name(self):
        return self._host.VOLTAGE_SENSORS[self._host.sensor_index][0]

    def get_value(self):
        host = self._host
        value = 0
        hwmon_node = ""
        sysfs_node = ""
        i2c_addr = host.VOLTAGE_SENSORS[host.sensor_index][5]
        i2c_addr_pattern = "-{:04x}".format(i2c_addr)
        label_str = host.VOLTAGE_SENSORS[host.sensor_index][6]
        multi_factor = host.VOLTAGE_SENSORS[host.sensor_index][7]

        cmd_str = "ls -l /sys/class/hwmon | grep \"\\%s\" | awk \"{print \\$9}\"" % (i2c_addr_pattern)

        try:
            hwmon_node = subprocess.check_output(cmd_str, shell=True).strip().decode("utf-8")

        except (OSError, subprocess.CalledProcessError) as e:
            log_err("Failed to get hwmon path for sensorn at %s, cmd_str - %s, exception %s" % (i2c_addr, cmd_str, e) )
            return 0

        hwmon_path = "/sys/class/hwmon/%s" % (hwmon_node)
        label_files = glob.glob(os.path.join(hwmon_path, "in*_label"))
        for label_file in label_files:
            try:
                with open(label_file, 'r') as f:
                    content = f.read().strip()
                    if content == label_str:
                        sysfs_node = label_file
                        break
            except Exception as e:
                log_err("Error Reading file %s, exception %s" % (label_file, e))
                return 0

        if sysfs_node == "":
            log_err("No hwmod node found for sensor at %s, hwmon - %s" % (i2c_addr, hwmon_path) )
            return 0

        voltage_node = sysfs_node.replace("label", "input")
        cmd_str = "cat %s" % (voltage_node)
        try:
            value = subprocess.check_output(cmd_str, shell=True).strip().decode("utf-8")

        except (OSError, subprocess.CalledProcessError) as e:
            log_err("Failed to read sensor at %s, voltage_node - %sexception %s" % (i2c_addr, voltage_node, e) )
            return 0

        voltage_value = int(value) * multi_factor
        return int(voltage_value)

    def get_high_threshold(self):
        return self._host.VOLTAGE_SENSORS[self._host.sensor_index][1]

    def get_low_threshold(self):
        return self._host.VOLTAGE_SENSORS[self._host.sensor_index][2]

    def set_high_threshold(self, value):
        raise NotImplementedError

    def set_low_threshold(self, value):
        raise NotImplementedError

    def get_high_critical_threshold(self):
        return self._host.VOLTAGE_SENSORS[self._host.sensor_index][3]

    def get_low_critical_threshold(self):
        return self._host.VOLTAGE_SENSORS[self._host.sensor_index][4]

    def set_high_critical_threshold(self, value):
        raise NotImplementedError

    def set_low_critical_threshold(self, value):
        raise NotImplementedError

    def get_minimum_recorded(self):
        return 10.4

    def get_maximum_recorded(self):
        return 25.0

    def get_presence(self):
        return True

    def get_model(self):
        return 'NA'

    def get_serial(self):
        return 'NA'

    def get_status(self):
        return True

    def get_position_in_parent(self):
        return self._host.sensor_index

    def is_replaceable(self):
        return False

    def get_revision(self):
        return 'NA'
