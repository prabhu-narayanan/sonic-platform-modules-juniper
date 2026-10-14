"""
sonic_alarm.constants -- All string constants, file paths, default intervals,
and hard limits for alarmd.

No logic lives here.  Every module imports from this file rather than
defining its own magic strings.
"""

# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------
SYSLOG_IDENTIFIER = 'alarmd'

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
STATE_DB = 'STATE_DB'
SYSTEM_ALARMS_TABLE = 'SYSTEM_ALARMS'

# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------
MACHINE_CONF = '/host/machine.conf'
DEVICE_BASE = '/usr/share/sonic/device'
ALARM_DEFS_FILENAME = 'alarm_defs.json'
ALARM_SCRIPTS_DIR = '/etc/sonic/alarm_scripts'
SONIC_VERSION_FILE = '/etc/sonic/sonic_version.yml'
COMMON_ALARM_DEFS_FILENAME = 'common_alarm_defs.json'

# ---------------------------------------------------------------------------
# Default intervals
# ---------------------------------------------------------------------------
DEFAULT_STATEDB_INTERVAL = 3       # seconds between statedb polls
DEFAULT_SCRIPT_INTERVAL = 60       # seconds between script runs
SCRIPT_TIMEOUT = 10                # default per-script timeout in seconds

# ---------------------------------------------------------------------------
# Hard limits -- prevent misconfigured alarm_defs from overusing resources.
# Validated via scalability testing on x86_64-juniper_qfx5241-r0 (March 2026).
# See tests/stress/STRESS_TEST_RESULTS.md for methodology and raw data.
# ---------------------------------------------------------------------------
MAX_STATEDB_CHECKS = 200           # absolute cap on statedb field evaluations
MAX_SCRIPT_CHECKS = 50             # absolute cap on script alarm definitions
MIN_STATEDB_INTERVAL = 2           # seconds -- floor for statedb poll interval
MIN_SCRIPT_INTERVAL = 30           # seconds -- floor for script poll interval
MAX_SCRIPT_TIMEOUT = 30            # seconds -- ceiling for any single script

# ---------------------------------------------------------------------------
# PID file -- used for single-instance enforcement via fcntl.flock()
# ---------------------------------------------------------------------------
PIDFILE_PATH = '/var/run/alarmd.pid'

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
VALID_SEVERITIES = {'Critical', 'Major', 'Minor', 'Warning'}
VALID_OPERATORS = {'==', '!=', '<', '>', '<=', '>='}
