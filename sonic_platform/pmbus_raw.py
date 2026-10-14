#!/usr/bin/env python3

import math

try:
    from smbus2 import SMBus
except ImportError:
    SMBus = None


PMBUS_READ_VIN = 0x88
PMBUS_READ_IIN = 0x89
PMBUS_READ_VOUT = 0x8B
PMBUS_READ_IOUT = 0x8C
PMBUS_READ_POUT = 0x96
PMBUS_READ_PIN = 0x97
PMBUS_VOUT_MODE = 0x20


class PmbusReadError(Exception):
    pass


def _signed(value, bits):
    sign_bit = 1 << (bits - 1)
    if value & sign_bit:
        value -= 1 << bits
    return value


def decode_linear11(raw_value):
    if raw_value in (0xFFFF, 0x7FFF):
        return None
    exponent = _signed((raw_value >> 11) & 0x1F, 5)
    mantissa = _signed(raw_value & 0x7FF, 11)
    return mantissa * math.pow(2, exponent)


def decode_linear16(raw_value, vout_mode):
    if raw_value in (0xFFFF, 0x7FFF):
        return None
    if vout_mode is None or (vout_mode & 0xE0) != 0:
        return None
    exponent = _signed(vout_mode & 0x1F, 5)
    return raw_value * math.pow(2, exponent)


def resolve_i2c_bus(pddf_obj, parent_bus):
    if parent_bus is None:
        return None
    if isinstance(parent_bus, int):
        return parent_bus
    parent_bus = str(parent_bus)
    try:
        return int(parent_bus, 0)
    except ValueError:
        pass
    if pddf_obj is None or not hasattr(pddf_obj, 'bus_resolver'):
        return None
    try:
        return pddf_obj.bus_resolver.resolve_parent_bus(parent_bus)
    except Exception:
        return None


class PmbusReader(object):
    @staticmethod
    def read_byte(bus_num, address, register):
        if SMBus is None:
            raise PmbusReadError('smbus2 is not available')
        with SMBus(bus_num) as bus:
            return bus.read_byte_data(address, register, force=True)

    @staticmethod
    def read_word(bus_num, address, register):
        if SMBus is None:
            raise PmbusReadError('smbus2 is not available')
        with SMBus(bus_num) as bus:
            return bus.read_word_data(address, register, force=True)

    @staticmethod
    def read_value(bus_num, address, register, value_format):
        raw_value = PmbusReader.read_word(bus_num, address, register)
        if value_format == 'linear16_vout':
            vout_mode = PmbusReader.read_byte(bus_num, address, PMBUS_VOUT_MODE)
            return decode_linear16(raw_value, vout_mode)
        return decode_linear11(raw_value)


class PmbusSensorBase(object):
    SENSOR_PREFIX = ''
    DEFAULT_UNIT = ''

    def __init__(self, index, pddf_data=None, pddf_plugin_data=None):
        self.index = index
        self.pddf_obj = pddf_data
        self.plugin_data = pddf_plugin_data
        self._minimum_recorded = None
        self._maximum_recorded = None
        self._config = self._load_config(index)

    def _load_config(self, index):
        key = '{}{}'.format(self.SENSOR_PREFIX, index + 1)
        if self.pddf_obj is None or key not in self.pddf_obj.data:
            return {}

        sensor_data = self.pddf_obj.data[key]
        topo_info = sensor_data.get('i2c', {}).get('topo_info', {})
        dev_attr = sensor_data.get('dev_attr', {})
        parent_bus = dev_attr.get(
            'pmbus_bus', dev_attr.get('parent_bus', topo_info.get('parent_bus')))
        bus_num = resolve_i2c_bus(self.pddf_obj, parent_bus)
        address = dev_attr.get('pmbus_addr', dev_attr.get('dev_addr', topo_info.get('dev_addr')))
        register = dev_attr.get('register', topo_info.get('register'))

        return {
            'name': dev_attr.get('display_name', key),
            'unit': dev_attr.get('unit', self.DEFAULT_UNIT),
            'bus_num': bus_num,
            'address': int(address, 0) if address is not None else None,
            'register': int(register, 0) if register is not None else None,
            'format': dev_attr.get('format', 'linear11'),
            'scale': float(dev_attr.get('scale', '1.0')),
            'precision': int(dev_attr.get('precision', '3')),
            'high_threshold': dev_attr.get('high_threshold'),
            'low_threshold': dev_attr.get('low_threshold'),
            'critical_high_threshold': dev_attr.get('critical_high_threshold'),
            'critical_low_threshold': dev_attr.get('critical_low_threshold'),
        }

    def _threshold(self, name):
        value = self._config.get(name)
        if value is None or value == '':
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return value

    def get_name(self):
        return self._config.get('name', '{}{}'.format(self.SENSOR_PREFIX, self.index + 1))

    def get_value(self):
        bus_num = self._config.get('bus_num')
        address = self._config.get('address')
        register = self._config.get('register')
        if bus_num is None or address is None or register is None:
            return None
        try:
            value = PmbusReader.read_value(bus_num, address, register, self._config.get('format'))
        except Exception:
            return None
        if value is None:
            return None
        value *= self._config.get('scale', 1.0)
        if value < 0:
            return None
        precision = self._config.get('precision', 3)
        value = round(value, precision)
        if self._minimum_recorded is None or value < self._minimum_recorded:
            self._minimum_recorded = value
        if self._maximum_recorded is None or value > self._maximum_recorded:
            self._maximum_recorded = value
        return value

    def get_unit(self):
        return self._config.get('unit', self.DEFAULT_UNIT)

    def get_minimum_recorded(self):
        return self._minimum_recorded

    def get_maximum_recorded(self):
        return self._maximum_recorded

    def get_high_threshold(self):
        return self._threshold('high_threshold')

    def get_low_threshold(self):
        return self._threshold('low_threshold')

    def get_high_critical_threshold(self):
        return self._threshold('critical_high_threshold')

    def get_low_critical_threshold(self):
        return self._threshold('critical_low_threshold')

    def is_replaceable(self):
        return False

    def get_position_in_parent(self):
        return self.index + 1
