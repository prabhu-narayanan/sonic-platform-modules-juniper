"""
sonic_alarm.alarm_store -- Manages the SYSTEM_ALARMS table in STATE_DB.

AlarmStore is the single writer to SYSTEM_ALARMS.  All raise/clear
operations go through this class, which enforces:
  - Write-once: won't re-write an alarm that's already active.
  - Delete-on-clear: removes the DB key entirely.
  - Thread-safe via a simple lock.

Logging: module-level SysLogger (identifier 'alarmd#store'), following
the same pattern as system-health/service_checker.py.
"""

import logging
import threading
from datetime import datetime, timezone

from logging.handlers import SysLogHandler
from sonic_py_common.syslogger import SysLogger
from swsscommon.swsscommon import FieldValuePairs

logger = SysLogger(
    log_identifier='alarmd#store',
    log_facility=SysLogHandler.LOG_DAEMON,
    log_level=logging.INFO,
    enable_runtime_config=False
)


class AlarmStore:
    """
    Manages the SYSTEM_ALARMS table in STATE_DB.

    Parameters
    ----------
    alarm_defs : dict
        Parsed alarm definitions -- used to build the alarm_id -> metadata
        lookup (severity, category, description_template, source).
    alarms_table : swsscommon.Table
        Table object bound to SYSTEM_ALARMS in STATE_DB.
    """

    def __init__(self, alarm_defs, alarms_table):
        self._table = alarms_table
        self._lock = threading.Lock()
        self._active = set()           # set of "alarm_id|object_name"

        # alarm_id -> metadata dict
        self._meta = {}
        self._rebuild_meta(alarm_defs)

    # -- metadata management -------------------------------------------------

    def _rebuild_meta(self, alarm_defs):
        """(Re)build the alarm_id -> metadata lookup from alarm definitions.

        Called once at init and again on SIGHUP reload so that newly-added
        alarm_ids get proper severity/category/template entries.
        """
        self._meta = {}
        for table in alarm_defs.get('alarm_tables', []):
            # Derive source automatically from table_name (statedb) or
            # group_name (script) — no manual source_daemon declaration.
            source = table.get('table_name',
                               table.get('group_name', 'alarmd'))
            for check in table.get('checks', []):
                aid = check.get('alarm_id')
                if aid and aid not in self._meta:
                    self._meta[aid] = {
                        'severity': check.get('severity', 'Minor'),
                        'category': check.get('category', 'System'),
                        'description_template': check.get(
                            'description_template', '{alarm_id}'),
                        'source': source,
                    }

    def known_alarm_ids(self):
        """Return the set of alarm_ids currently in the metadata lookup."""
        return set(self._meta.keys())

    # -- public API -----------------------------------------------------------

    def set_alarm(self, alarm_id, object_name, is_fault, description=None):
        """Raise or clear an alarm based on the boolean *is_fault*.

        This is the primary entry point used by StateDBPoller.
        """
        if is_fault:
            self.raise_alarm(alarm_id, object_name, description=description)
        else:
            self.clear_alarm(alarm_id, object_name)

    def raise_alarm(self, alarm_id, object_name, description=None):
        """Raise (create) an alarm.  No-op if already active."""
        tag = f"{alarm_id}|{object_name}"
        with self._lock:
            if tag in self._active:
                return
            self._active.add(tag)

        meta = self._meta.get(alarm_id, {})
        severity = meta.get('severity', 'Minor')
        category = meta.get('category', 'System')
        source = meta.get('source', 'alarmd')
        tmpl = meta.get('description_template', '{alarm_id}')

        if description is None:
            description = tmpl.replace('{object_name}', object_name) \
                              .replace('{alarm_id}', alarm_id)

        now_ms = datetime.now(timezone.utc).strftime(
            '%Y-%m-%d %H:%M:%S.%f')[:-3]

        key = f"{alarm_id}|{object_name}"
        fvs = FieldValuePairs([
            ('alarm_id',      alarm_id),
            ('object_name',   object_name),
            ('severity',      severity),
            ('category',      category),
            ('source',        source),
            ('description',   description),
            ('time_created',  now_ms),
            ('status',        'active'),
        ])

        try:
            self._table.set(key, fvs)
            logger.log_warning(
                f"ALARM RAISED: {alarm_id} on {object_name} "
                f"[{severity}] — {description}")
        except Exception as exc:
            logger.log_error(f"DB write failed for {key}: {exc}")
            with self._lock:
                self._active.discard(tag)

    def clear_alarm(self, alarm_id, object_name):
        """Clear an alarm by deleting its DB key.  No-op if not active."""
        tag = f"{alarm_id}|{object_name}"
        with self._lock:
            if tag not in self._active:
                return
            self._active.discard(tag)

        key = f"{alarm_id}|{object_name}"
        try:
            self._table._del(key)
            logger.log_info(f"ALARM CLEARED: {alarm_id} on {object_name}")
        except Exception as exc:
            logger.log_error(f"DB delete failed for {key}: {exc}")
            with self._lock:
                self._active.add(tag)    # rollback so next cycle retries

    def clear_all(self):
        """Clear every alarm this instance has raised."""
        with self._lock:
            tags = list(self._active)
            self._active.clear()

        for tag in tags:
            try:
                self._table._del(tag)
                logger.log_info(f"ALARM CLEARED (shutdown): {tag}")
            except Exception as exc:
                logger.log_error(f"DB delete failed for {tag}: {exc}")

    def purge_stale_alarms(self, valid_alarm_ids):
        """Clear any active alarms whose alarm_id is no longer in the config.

        Called after a SIGHUP reload to remove alarms that no longer have a
        definition.  Returns the list of tags that were purged.
        """
        purged = []
        with self._lock:
            stale_tags = [
                tag for tag in self._active
                if tag.split('|', 1)[0] not in valid_alarm_ids
            ]
            for tag in stale_tags:
                self._active.discard(tag)
                purged.append(tag)

        for tag in purged:
            try:
                self._table._del(tag)
                logger.log_info(
                    f"ALARM PURGED (stale after reload): {tag}")
            except Exception as exc:
                logger.log_error(
                    f"DB delete failed for stale alarm {tag}: {exc}")
        return purged

    def sync_active_set(self):
        """On startup, scan STATE_DB for any SYSTEM_ALARMS keys so the
        in-memory active set reflects reality (survives alarmd restart).
        """
        try:
            keys = self._table.getKeys()
            for key in keys:
                with self._lock:
                    self._active.add(key)
            logger.log_info(
                f"Synced {len(self._active)} active alarms from STATE_DB")
        except Exception as exc:
            logger.log_warning(f"Could not sync active alarms: {exc}")

    def clear_on_startup(self):
        """Delete all pre-existing SYSTEM_ALARMS entries from STATE_DB.

        Called once at startup.  The first poll cycle re-raises alarms
        for faults that genuinely still exist.  This prevents stale
        alarms from surviving across warmboots (where STATE_DB is
        preserved).
        """
        try:
            keys = self._table.getKeys()
        except Exception as exc:
            logger.log_warning(
                f"Could not read SYSTEM_ALARMS keys for "
                f"startup cleanup: {exc}")
            return

        for key in keys:
            try:
                self._table._del(key)
                logger.log_info(f"ALARM CLEARED (startup gc): {key}")
            except Exception as exc:
                logger.log_error(
                    f"DB delete failed for startup gc {key}: {exc}")

        with self._lock:
            self._active.clear()

        logger.log_info(
            f"clear_on_startup: removed {len(keys)} stale alarm(s)")

    @property
    def active_count(self):
        """Return the number of currently active alarms."""
        with self._lock:
            return len(self._active)

    @property
    def active_tags(self):
        """Return a frozen copy of the active alarm tags."""
        with self._lock:
            return frozenset(self._active)
