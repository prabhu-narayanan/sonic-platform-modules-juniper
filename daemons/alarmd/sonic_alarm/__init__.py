"""
sonic_alarm -- SONiC Alarm Monitoring Daemon package.

Provides the core components for alarmd:
  - AlarmStore        : manages SYSTEM_ALARMS table in STATE_DB
  - StateDBPoller     : polls STATE_DB tables and evaluates conditions
  - ScriptRunner      : executes external health-check scripts
  - config            : alarm definition loading, merging, validation
  - constants         : all string constants, paths, limits
"""

__version__ = '1.0.0'

from sonic_alarm.alarm_store import AlarmStore
from sonic_alarm.statedb_poller import StateDBPoller, evaluate_condition
from sonic_alarm.script_runner import ScriptRunner

__all__ = [
    'AlarmStore',
    'StateDBPoller',
    'ScriptRunner',
    'evaluate_condition',
]
