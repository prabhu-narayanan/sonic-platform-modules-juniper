#!/usr/bin/env python3
#
# thermal.py — PDDF Thermal wrapper with JSON-driven thresholds
#
# All threshold values are read from pddf-device.json TEMP{N}.i2c.dev_attr,
# or PSU{N}.dev_attr for PSU thermals.
# No platform-specific constants — new platforms only need JSON entries.
#
# Copyright (c) 2025, Juniper Networks, Inc.
# All rights reserved.
#
import os
import glob

try:
    from sonic_platform_pddf_base.pddf_thermal import PddfThermal
except ImportError as e:
    raise ImportError("%s - required module not found" % e)


class Thermal(PddfThermal):
    """PDDF Thermal sensor with JSON-driven alarm/policy thresholds.

    Standard SONiC thresholds (high_threshold, high_crit_threshold) are
    served by the PddfThermal base via dev_info overrides or hwmon sysfs.

    Custom policy thresholds used by thermal_infos.py for fan-speed curve
    and alarm classification are read from TEMP{N}.i2c.dev_attr:
        wtc               — warm temperature control (fan speed baseline)
        wt                — warm threshold (fan speed ramp start)
        high_threshold     — high threshold (normal fan)
        high_threshold_bad_fan — high threshold (degraded fan)
        yat               — yellow alarm threshold
        yat_bad_fan       — yellow alarm threshold (degraded fan)
        rat               — red alarm threshold (shutdown trigger)
        rat_bad_fan       — red alarm threshold (degraded fan)
        fire_threshold     — fire threshold (immediate shutdown)
    """

    def __init__(self, index, pddf_data=None, pddf_plugin_data=None,
                 is_psu_thermal=False, psu_index=0):
        PddfThermal.__init__(self, index, pddf_data, pddf_plugin_data,
                             is_psu_thermal, psu_index)
        from sonic_platform.override import load_impl
        self._impl = load_impl("Thermal", self)

    def get_name(self):
        return self._impl.get_name()

    def get_presence(self):
        return self._impl.get_presence()

    def get_status(self):
        return self._impl.get_status()

    def get_model(self):
        return self._impl.get_model()

    def get_serial(self):
        return self._impl.get_serial()

    def is_replaceable(self):
        return self._impl.is_replaceable()

    def get_position_in_parent(self):
        return self._impl.get_position_in_parent()

    def get_temperature(self):
        return self._impl.get_temperature()

    def get_minimum_recorded(self):
        return self._impl.get_minimum_recorded()

    def get_maximum_recorded(self):
        return self._impl.get_maximum_recorded()

    def get_high_threshold(self):
        return self._impl.get_high_threshold()

    def get_high_critical_threshold(self):
        return self._impl.get_high_critical_threshold()

    def get_low_threshold(self):
        return self._impl.get_low_threshold()

    def get_low_critical_threshold(self):
        return self._impl.get_low_critical_threshold()

    def get_WTC(self):
        return self._impl.get_WTC()

    def get_WT(self):
        return self._impl.get_WT()

    def get_YAT(self):
        return self._impl.get_YAT()

    def get_YATBF(self):
        return self._impl.get_YATBF()

    def get_RAT(self):
        return self._impl.get_RAT()

    def get_RATBF(self):
        return self._impl.get_RATBF()

    def get_FT(self):
        return self._impl.get_FT()

    def get_high_threshold_bad_fan(self):
        return self._impl.get_high_threshold_bad_fan()

    # ------------------------------------------------------------------ #
    #  Helper: read a float from JSON dev_attr                            #
    # ------------------------------------------------------------------ #
    def _threshold_obj(self):
        """dev_attr dict holding this sensor's thresholds.

        PddfThermal.__init__ derives thermal_obj from the per-PSU thermal
        index, so every PSU thermal lands on TEMP1 and would otherwise
        inherit an unrelated board sensor's limits. For PSU thermals read
        the PSU{n} node's own dev_attr instead.
        """
        if self.is_psu_thermal:
            return self.pddf_obj.data.get(
                "PSU{}".format(self.thermals_psu_index), {}).get('dev_attr', {})
        return self.thermal_obj['i2c']['dev_attr']

    def _get_dev_attr(self, key, default=None):
        """Read a numeric threshold from the JSON dev_attr section."""
        try:
            val = self._threshold_obj().get(key)
            return float(val) if val is not None else default
        except (KeyError, TypeError, ValueError):
            return default

    # ------------------------------------------------------------------ #
    #  IIO subsystem support (e.g. hdc2010 humidity/temp sensor)         #
    # ------------------------------------------------------------------ #
    def _is_iio_device(self):
        """Check if this thermal sensor uses the IIO subsystem (e.g. hdc2010)."""
        try:
            attr_list = self.thermal_obj.get('i2c', {}).get('attr_list', [])
            for attr in attr_list:
                if isinstance(attr, dict) and attr.get('attr_devtype') == 'iio':
                    return True
        except Exception:
            pass
        return False

    def _get_iio_temperature(self):
        """Read temperature for IIO-type sensors (e.g. hdc2010).

        Tries two methods in order:
        1) IIO sysfs:  /sys/bus/i2c/devices/<bus>-<addr>/iio:device*/
        2) SMBus raw:  read HDC2010 registers 0x00-0x01 via smbus2

        Method 2 works even when the hdc2010 kernel IIO driver is not
        loaded, which is the common case on SONiC.
        """
        topo = self.thermal_obj.get('i2c', {}).get('topo_info', {})
        dev_addr = topo.get('dev_addr', '')
        dev_addr_hex = dev_addr.replace('0x', '').lower()

        # --- Method 1: IIO sysfs ---
        try:
            for pad in (dev_addr_hex, dev_addr_hex.zfill(4)):
                pattern = '/sys/bus/i2c/devices/*-{}/iio:device*'.format(pad)
                iio_paths = glob.glob(pattern)
                if iio_paths:
                    iio_path = iio_paths[0]
                    raw = float(open(os.path.join(iio_path, 'in_temp_raw')).read().strip())
                    scale = float(open(os.path.join(iio_path, 'in_temp_scale')).read().strip())
                    offset = float(open(os.path.join(iio_path, 'in_temp_offset')).read().strip())
                    return round((raw + offset) * scale / 1000.0, 3)
        except Exception:
            pass

        # --- Method 2: SMBus raw read (HDC2010 registers) ---
        try:
            import smbus2
            bus_num = int(topo.get('parent_bus', '0'), 0)
            addr = int(dev_addr, 0)
            bus = smbus2.SMBus(bus_num)
            try:
                # Trigger measurement (reg 0x0F bit 0)
                bus.write_byte_data(addr, 0x0F, 0x01)
                # Read temperature registers (LSB=0x00, MSB=0x01)
                lsb = bus.read_byte_data(addr, 0x00)
                msb = bus.read_byte_data(addr, 0x01)
                raw = (msb << 8) | lsb
                temp = (raw / 65536.0) * 165.0 - 40.0
                return round(temp, 3)
            finally:
                bus.close()
        except Exception as e:
            print("IIO/SMBus temperature read error for {}: {}".format(
                self.thermal_obj_name, e))
        return None

    def _read_psu_pmbus_temp(self, attr):
        """Read a PSU temp{index}_<attr> (°C) from the generic 'pmbus' hwmon.

        On QFX5220, the PSU PMBus (0x58) is instantiated by platform_init and
        bound to the generic Linux 'pmbus' driver (pddf_psu_driver_module is
        blacklisted), which exposes temp{N}_input / temp{N}_max / temp{N}_crit
        (m°C).  Resolve the PSU PMBus hwmon directory from PSU{N}_PMBUS topo_info
        and read the attribute directly.
        """
        try:
            pmbus_key = "PSU{}_PMBUS".format(self.thermals_psu_index)
            topo = self.pddf_obj.data.get(pmbus_key, {}).get(
                'i2c', {}).get('topo_info', {})
            bus = int(topo.get('parent_bus', '0'), 0)
            addr = int(topo.get('dev_addr', '0'), 0)
            pmbus_dir = '/sys/bus/i2c/devices/{}-{:04x}'.format(bus, addr)
            for hwmon in glob.glob(os.path.join(pmbus_dir, 'hwmon', 'hwmon*')):
                path = os.path.join(
                    hwmon, 'temp{}_{}'.format(self.thermal_index, attr))
                try:
                    with open(path) as f:
                        return round(int(f.read().strip()) / 1000.0, 1)
                except (OSError, ValueError):
                    continue
        except Exception:
            pass
        return None

    def _get_psu_hwmon_temperature(self):
        """Current PSU temperature (°C) from the pmbus hwmon temp{N}_input."""
        return self._read_psu_pmbus_temp('input')

    def _get_psu_pddf_high_threshold(self):
        """PMBus MFR_MAX_TEMP_1 (0xc0) via the PDDF psu_temp{N}_high_threshold sysfs."""
        try:
            return super().get_high_threshold()
        except (NotImplementedError, TypeError, ValueError):
            return None

