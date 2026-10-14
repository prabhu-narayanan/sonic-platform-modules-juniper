"""
    sensor.py

    Legacy table-driven voltage sensor (reads voltage_sensors.json rows), used
    by the older dep chassis via `from sonic_platform.sensor import VoltageSensor`.
    Distinct from voltage_sensor.py, which is the PDDF-driven VoltageSensor built
    by the shipped PddfChassis. Kept separate on purpose; do not merge.
"""

from sonic_platform_base.sensor_base import VoltageSensorBase


class VoltageSensor(VoltageSensorBase):

    def __init__(self, sensor_idx, voltage_data):
        VoltageSensorBase.__init__(self)
        from sonic_platform.override import load_impl
        self._impl = load_impl("Sensor", self)
        self.sensor_index = sensor_idx
        self.VOLTAGE_SENSORS = voltage_data

    def get_name(self):
        return self._impl.get_name()

    def get_value(self):
        return self._impl.get_value()

    def get_high_threshold(self):
        return self._impl.get_high_threshold()

    def get_low_threshold(self):
        return self._impl.get_low_threshold()

    def set_high_threshold(self, value):
        return self._impl.set_high_threshold(value)

    def set_low_threshold(self, value):
        return self._impl.set_low_threshold(value)

    def get_high_critical_threshold(self):
        return self._impl.get_high_critical_threshold()

    def get_low_critical_threshold(self):
        return self._impl.get_low_critical_threshold()

    def set_high_critical_threshold(self, value):
        return self._impl.set_high_critical_threshold(value)

    def set_low_critical_threshold(self, value):
        return self._impl.set_low_critical_threshold(value)

    def get_minimum_recorded(self):
        return self._impl.get_minimum_recorded()

    def get_maximum_recorded(self):
        return self._impl.get_maximum_recorded()

    def get_presence(self):
        return self._impl.get_presence()

    def get_model(self):
        return self._impl.get_model()

    def get_serial(self):
        return self._impl.get_serial()

    def get_status(self):
        return self._impl.get_status()

    def get_position_in_parent(self):
        return self._impl.get_position_in_parent()

    def is_replaceable(self):
        return self._impl.is_replaceable()

    def get_revision(self):
        return self._impl.get_revision()
