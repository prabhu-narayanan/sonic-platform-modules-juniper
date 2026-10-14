import json
import logging

try:
    from sonic_platform_base.sonic_thermal_control.thermal_manager_base import ThermalManagerBase
    from .thermal_actions import *
    from .thermal_conditions import *
    from .thermal_infos import *
    from .leak_policy import *
except ImportError as e:
    raise ImportError(str(e) + ' - required module not found') from e

logger = logging.getLogger(__name__)

# Path to PDDF JSON on the running switch
_PDDF_JSON_PATH = '/usr/share/sonic/platform/pddf/pddf-device.json'
_DEFAULT_INTERVAL = 15


class ThermalManager(ThermalManagerBase):
    _interval = None

    @classmethod
    def get_interval(cls):
        """Return thermal daemon poll interval (seconds) from THERMAL_CTRL JSON."""
        if cls._interval is None:
            try:
                with open(_PDDF_JSON_PATH) as f:
                    data = json.load(f)
                thermal_ctrl = data.get('THERMAL_CTRL', {}).get('dev_attr', {})
                cls._interval = int(thermal_ctrl.get(
                    'thermald_interval', _DEFAULT_INTERVAL))
            except Exception as e:
                logger.warning("Failed to read poll interval from %s: %s; "
                               "using default %ds",
                               _PDDF_JSON_PATH, e, _DEFAULT_INTERVAL)
                cls._interval = _DEFAULT_INTERVAL
        return cls._interval
