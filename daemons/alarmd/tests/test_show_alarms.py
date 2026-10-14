"""
test_show_alarms.py — Unit tests for the 'show alarms' CLI command

Tests all output modes: table, JSON, summary, grouped, filtered.
Mocks SonicV2Connector so tests run without Redis.

Run:
    python3 -m pytest tests/test_show_alarms.py -v
"""

import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from click.testing import CliRunner

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ALARMD_DIR = os.path.dirname(TEST_DIR)
# show/alarms.py lives in sonic-utilities — walk up from the sonic-platform submodule
# to sonic-buildimage root (6 levels up):
#   alarmd/ -> daemons/ -> common/ -> platform/ -> sonic-platform/ -> modules/ -> sonic-buildimage/
def walk_up(path, levels):
    for _ in range(levels):
        path = os.path.dirname(path)
    return path
REPO_ROOT = walk_up(ALARMD_DIR, 6)  # .../sonic-buildimage
SHOW_DIR = os.path.join(REPO_ROOT, 'src', 'sonic-utilities', 'show')

if not os.path.isdir(SHOW_DIR):
    raise unittest.SkipTest(
        f"sonic-utilities show/ not found at {SHOW_DIR} — "
        "test_show_alarms requires the full sonic-buildimage tree")

# Add show/ to path so we can import alarms.py
sys.path.insert(0, SHOW_DIR)
sys.path.insert(0, ALARMD_DIR)

# ---------------------------------------------------------------------------
# Mock data — simulates what _read_alarms() returns from Redis
# ---------------------------------------------------------------------------
MOCK_ALARMS = [
    {
        'alarm_id': 'PSU_MISSING',
        'object_name': 'PSU2',
        'severity': 'Critical',
        'category': 'Hardware',
        'source': 'PSU_INFO',
        'description': 'PSU2 Absent',
        'time_created': '2026-03-04 10:00:00.123',
        'status': 'active',
    },
    {
        'alarm_id': 'FAN_FAULT',
        'object_name': 'FAN3',
        'severity': 'Major',
        'category': 'Hardware',
        'source': 'FAN_INFO',
        'description': 'FAN3 Fault',
        'time_created': '2026-03-04 10:01:00.456',
        'status': 'active',
    },
    {
        'alarm_id': 'DISK_USAGE_HIGH',
        'object_name': 'root-partition',
        'severity': 'Major',
        'category': 'System',
        'source': 'system_scripts',
        'description': 'Root partition usage above threshold — 95% used on / (threshold 90%)',
        'time_created': '2026-03-04 10:02:00.789',
        'status': 'active',
    },
    {
        'alarm_id': 'CPU_USAGE_HIGH',
        'object_name': 'SYSTEM',
        'severity': 'Minor',
        'category': 'System',
        'source': 'system_scripts',
        'description': 'CPU usage above threshold',
        'time_created': '2026-03-04 10:03:00.000',
        'status': 'active',
    },
]

NO_ALARMS = []


# ---------------------------------------------------------------------------
# Import the CLI module with mocked swsscommon
# ---------------------------------------------------------------------------
# We need to mock swsscommon before importing alarms.py
mock_swsscommon = MagicMock()
sys.modules['swsscommon'] = mock_swsscommon
sys.modules['swsscommon.swsscommon'] = mock_swsscommon

import alarms as alarms_module


class TestShowAlarms(unittest.TestCase):
    """Tests for the 'show alarms' CLI command."""

    def setUp(self):
        self.runner = CliRunner()

    @patch.object(alarms_module, '_read_alarms', return_value=MOCK_ALARMS)
    def test_default_table_output(self, mock_read):
        result = self.runner.invoke(alarms_module.alarms, [])
        self.assertEqual(result.exit_code, 0)
        self.assertIn('PSU_MISSING', result.output)
        self.assertIn('FAN_FAULT', result.output)
        self.assertIn('DISK_USAGE_HIGH', result.output)
        self.assertIn('Total: 4 active alarm(s)', result.output)

    @patch.object(alarms_module, '_read_alarms', return_value=MOCK_ALARMS)
    def test_severity_ordering(self, mock_read):
        """Critical should appear before Major, Major before Minor."""
        result = self.runner.invoke(alarms_module.alarms, [])
        crit_pos = result.output.index('Critical')
        major_pos = result.output.index('Major')
        minor_pos = result.output.index('Minor')
        self.assertLess(crit_pos, major_pos)
        self.assertLess(major_pos, minor_pos)

    @patch.object(alarms_module, '_read_alarms', return_value=MOCK_ALARMS)
    def test_filter_by_severity(self, mock_read):
        result = self.runner.invoke(alarms_module.alarms, ['-s', 'Critical'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn('PSU_MISSING', result.output)
        self.assertNotIn('FAN_FAULT', result.output)
        self.assertIn('Total: 1 active alarm(s)', result.output)

    @patch.object(alarms_module, '_read_alarms', return_value=MOCK_ALARMS)
    def test_filter_by_category(self, mock_read):
        result = self.runner.invoke(alarms_module.alarms, ['-c', 'System'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn('DISK_USAGE_HIGH', result.output)
        self.assertIn('CPU_USAGE_HIGH', result.output)
        self.assertNotIn('PSU_MISSING', result.output)
        self.assertIn('Total: 2 active alarm(s)', result.output)

    @patch.object(alarms_module, '_read_alarms', return_value=MOCK_ALARMS)
    def test_filter_by_object_name(self, mock_read):
        result = self.runner.invoke(alarms_module.alarms, ['-o', 'PSU2'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn('PSU_MISSING', result.output)
        self.assertNotIn('FAN_FAULT', result.output)
        self.assertIn('Total: 1 active alarm(s)', result.output)

    @patch.object(alarms_module, '_read_alarms', return_value=MOCK_ALARMS)
    def test_filter_case_insensitive(self, mock_read):
        result = self.runner.invoke(alarms_module.alarms, ['-s', 'critical'])
        self.assertIn('PSU_MISSING', result.output)

    @patch.object(alarms_module, '_read_alarms', return_value=MOCK_ALARMS)
    def test_json_output(self, mock_read):
        result = self.runner.invoke(alarms_module.alarms, ['--json'])
        self.assertEqual(result.exit_code, 0)
        data = json.loads(result.output)
        self.assertEqual(len(data), 4)
        alarm_ids = [a['alarm_id'] for a in data]
        self.assertIn('PSU_MISSING', alarm_ids)

    @patch.object(alarms_module, '_read_alarms', return_value=MOCK_ALARMS)
    def test_json_with_filter(self, mock_read):
        result = self.runner.invoke(alarms_module.alarms, ['--json', '-s', 'Critical'])
        data = json.loads(result.output)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['alarm_id'], 'PSU_MISSING')

    @patch.object(alarms_module, '_read_alarms', return_value=MOCK_ALARMS)
    def test_summary_output(self, mock_read):
        result = self.runner.invoke(alarms_module.alarms, ['--summary'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn('Critical', result.output)
        self.assertIn('Major', result.output)
        self.assertIn('Minor', result.output)
        self.assertIn('Total', result.output)

    @patch.object(alarms_module, '_read_alarms', return_value=MOCK_ALARMS)
    def test_group_by_severity(self, mock_read):
        result = self.runner.invoke(alarms_module.alarms, ['-g', 'severity'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn('severity: Critical', result.output)
        self.assertIn('severity: Major', result.output)
        self.assertIn('severity: Minor', result.output)

    @patch.object(alarms_module, '_read_alarms', return_value=MOCK_ALARMS)
    def test_group_by_category(self, mock_read):
        result = self.runner.invoke(alarms_module.alarms, ['-g', 'category'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn('category: Hardware', result.output)
        self.assertIn('category: System', result.output)

    @patch.object(alarms_module, '_read_alarms', return_value=NO_ALARMS)
    def test_no_alarms(self, mock_read):
        result = self.runner.invoke(alarms_module.alarms, [])
        self.assertEqual(result.exit_code, 0)
        self.assertIn('No active alarms', result.output)

    @patch.object(alarms_module, '_read_alarms', return_value=NO_ALARMS)
    def test_no_alarms_summary(self, mock_read):
        result = self.runner.invoke(alarms_module.alarms, ['--summary'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn('Total', result.output)

    @patch.object(alarms_module, '_read_alarms', return_value=MOCK_ALARMS)
    def test_combined_filters(self, mock_read):
        """Multiple filters should AND together."""
        result = self.runner.invoke(alarms_module.alarms, ['-c', 'System', '-s', 'Minor'])
        self.assertIn('CPU_USAGE_HIGH', result.output)
        self.assertNotIn('DISK_USAGE_HIGH', result.output)
        self.assertIn('Total: 1 active alarm(s)', result.output)

    @patch.object(alarms_module, '_read_alarms', return_value=MOCK_ALARMS)
    def test_filter_no_match(self, mock_read):
        result = self.runner.invoke(alarms_module.alarms, ['-o', 'NONEXISTENT'])
        self.assertIn('No active alarms', result.output)


class TestReadAlarms(unittest.TestCase):
    """Tests that exercise the _read_alarms() function body directly
    (lines 27-40) by mocking SonicV2Connector at the class level."""

    def _make_mock_db(self, keys, entries):
        """Build a mock SonicV2Connector that returns the given keys/entries.

        Parameters
        ----------
        keys : list[str] | None
            Return value for db.keys(). None simulates no keys found.
        entries : dict[str, dict | None]
            Map of key -> get_all return value.
        """
        mock_db = MagicMock()
        mock_db.STATE_DB = 'STATE_DB'
        mock_db.keys.return_value = keys
        mock_db.get_all.side_effect = lambda db, key: entries.get(key)
        return mock_db

    def test_read_alarms_happy_path(self):
        """_read_alarms() returns alarm dicts from Redis keys."""
        mock_db = self._make_mock_db(
            keys=['SYSTEM_ALARMS|PSU_MISSING|PSU 2',
                  'SYSTEM_ALARMS|FAN_FAULT|FAN 3'],
            entries={
                'SYSTEM_ALARMS|PSU_MISSING|PSU 2': {
                    'alarm_id': 'PSU_MISSING',
                    'object_name': 'PSU 2',
                    'severity': 'Critical',
                },
                'SYSTEM_ALARMS|FAN_FAULT|FAN 3': {
                    'alarm_id': 'FAN_FAULT',
                    'object_name': 'FAN 3',
                    'severity': 'Major',
                },
            },
        )
        MockConnector = MagicMock(return_value=mock_db)
        with patch.dict('sys.modules', {
            'swsscommon': MagicMock(),
            'swsscommon.swsscommon': MagicMock(SonicV2Connector=MockConnector),
        }):
            # Re-invoke the real function body
            result = alarms_module._read_alarms.__wrapped__() \
                if hasattr(alarms_module._read_alarms, '__wrapped__') \
                else self._call_read_alarms(MockConnector)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['alarm_id'], 'FAN_FAULT')   # sorted order
        self.assertEqual(result[1]['alarm_id'], 'PSU_MISSING')

    def test_read_alarms_no_keys(self):
        """_read_alarms() returns [] when Redis has no SYSTEM_ALARMS keys."""
        mock_db = self._make_mock_db(keys=None, entries={})
        MockConnector = MagicMock(return_value=mock_db)
        result = self._call_read_alarms(MockConnector)
        self.assertEqual(result, [])

    def test_read_alarms_get_all_returns_none(self):
        """_read_alarms() skips keys where get_all returns None."""
        mock_db = self._make_mock_db(
            keys=['SYSTEM_ALARMS|GHOST|X'],
            entries={'SYSTEM_ALARMS|GHOST|X': None},
        )
        MockConnector = MagicMock(return_value=mock_db)
        result = self._call_read_alarms(MockConnector)
        self.assertEqual(result, [])

    def test_read_alarms_exception(self):
        """_read_alarms() returns [] and prints error on exception."""
        MockConnector = MagicMock(side_effect=Exception("Redis down"))
        runner = CliRunner()
        # Use the CLI to capture stderr output from click.echo(..., err=True)
        with patch.object(alarms_module, '_read_alarms',
                          side_effect=None):
            # Actually call the real function through our helper
            result = self._call_read_alarms(MockConnector)
        self.assertEqual(result, [])

    @staticmethod
    def _call_read_alarms(MockConnector):
        """Call the real _read_alarms() body with a mocked SonicV2Connector.

        Temporarily patches the swsscommon module so the lazy import inside
        _read_alarms() picks up our mock.
        """
        mock_swss = MagicMock()
        mock_swss.SonicV2Connector = MockConnector
        with patch.dict('sys.modules', {
            'swsscommon': MagicMock(swsscommon=mock_swss),
            'swsscommon.swsscommon': mock_swss,
        }):
            # Force re-import of the function's lazy import by calling
            # the function body directly
            import importlib
            import alarms as _mod
            importlib.reload(_mod)
            return _mod._read_alarms()


if __name__ == '__main__':
    unittest.main()
