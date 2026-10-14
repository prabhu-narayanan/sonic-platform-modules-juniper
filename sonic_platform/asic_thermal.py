#!/usr/bin/env python3
#
# asic_thermal.py - Broadcom ASIC die-temperature thermal sensor
#
# The switch ASIC die temperature is read from STATE_DB:ASIC_TEMPERATURE_INFO,
# published by orchagent's SwitchOrch sensor poller via the SAI SDK API.
#
# Appears as "ASIC" in 'show platform temperature'.
#

try:
    from sonic_platform_base.thermal_base import ThermalBase
    from swsscommon.swsscommon import SonicV2Connector
except ImportError as e:
    raise ImportError("%s - required module not found" % e)


_ASIC_TEMP_INFO = "ASIC_TEMPERATURE_INFO"


class AsicThermal(ThermalBase):
    """ASIC die-temperature sensor backed by STATE_DB."""

    NAME = "ASIC"
    _THRESHOLD_KEY = "ASIC_THRESHOLDS"
    _THRESHOLDS = {
        'wtc': 87.0, 'wt': 94.0,
        'high_threshold': 107.0, 'ot': 110.0, 'fire_threshold': 115.0,
        'high_threshold_bad_fan': 107.0,
        'yat': 107.0, 'yat_bad_fan': 107.0,
        'rat': 110.0, 'rat_bad_fan': 110.0,
    }

    def __init__(self, index=0, position_offset=0, pddf_data=None):
        ThermalBase.__init__(self)
        self.is_asic_thermal = True
        from sonic_platform.override import load_impl
        self._impl = load_impl("AsicThermal", self)
        self._index = index
        self._state_db = None
        self._thresholds = self._load_thresholds(pddf_data)

    @classmethod
    def _load_thresholds(cls, pddf_data):
        thresholds = dict(cls._THRESHOLDS)
        try:
            overrides = pddf_data.data.get(cls._THRESHOLD_KEY) or {}
        except Exception:
            return thresholds
        for key, value in overrides.items():
            try:
                thresholds[key] = float(value)
            except (TypeError, ValueError):
                pass
        return thresholds

    def _get_state_db_conn(self):
        if self._state_db is None:
            try:
                self._state_db = SonicV2Connector(use_unix_socket_path=True)
            except TypeError:
                self._state_db = SonicV2Connector()
            self._state_db.connect(self._state_db.STATE_DB)
        return self._state_db

    def _get_asic_temp_info(self, db):
        data = db.get_all(db.STATE_DB, _ASIC_TEMP_INFO)
        if data:
            return data
        for key in sorted(db.keys(db.STATE_DB, _ASIC_TEMP_INFO + "*") or []):
            data = db.get_all(db.STATE_DB, key)
            if data:
                return data
        return None

    def _read_sdk_temp(self):
        """Return the maximum current die temperature in degrees C, or None."""
        try:
            data = self._get_asic_temp_info(self._get_state_db_conn())
            if not data:
                return None
            values = []
            for key, value in data.items():
                if key.startswith('temperature_'):
                    try:
                        values.append(float(value))
                    except (TypeError, ValueError):
                        pass
            if values:
                return max(values)
            for key in ('maximum_temperature', 'average_temperature'):
                try:
                    if data.get(key) is not None:
                        return float(data[key])
                except (TypeError, ValueError):
                    pass
        except Exception:
            pass
        return None

    def _thr(self, key):
        value = self._thresholds.get(key)
        return float(value) if value is not None else None

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

    def get_low_threshold(self):
        return self._impl.get_low_threshold()

    def get_high_critical_threshold(self):
        return self._impl.get_high_critical_threshold()

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
