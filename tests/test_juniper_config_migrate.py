"""Unit tests for common/utils/juniper_config_migrate.py and its config-setup hook.

A config_db.json saved by an older image can fail YANG validation, which makes
config-setup abort so that only database/gnmi/sysmgr start. The hook repairs the
two known causes after the old config is copied and before it is loaded.
"""

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.conftest import BASE_DIR, load_module

mod = load_module("juniper_config_migrate",
                  BASE_DIR / "common" / "utils" / "juniper_config_migrate.py")
HOOK = BASE_DIR / "common" / "config-setup" / "70-juniper-config-migration"
SCRIPT = BASE_DIR / "common" / "utils" / "juniper_config_migrate.py"

JMA_CONFIG = {
    "DC_JMA": {"config": {"epterm_ip": "10.0.0.1"}},
    "FEATURE": {"dc-jma": {"state": "enabled"}, "swss": {"state": "enabled"}},
    "AUTO_TECHSUPPORT_FEATURE": {"dc-jma": {"state": "disabled"}},
    "SYSLOG_CONFIG_FEATURE": {"dc-jma": {"rate_limit_interval": "300"}},
}


class TestMgmtPort(unittest.TestCase):

    def test_adds_port_for_mgmt_interface(self):
        cfg = {"MGMT_INTERFACE": {"eth0|10.1.1.1/24": {"gwaddr": "10.1.1.254"}}}
        self.assertEqual(mod.add_missing_mgmt_ports(cfg), ["eth0"])
        self.assertEqual(cfg["MGMT_PORT"], {"eth0": {"admin_status": "up"}})

    def test_keeps_existing_port_untouched(self):
        cfg = {"MGMT_INTERFACE": {"eth0|10.1.1.1/24": {}},
               "MGMT_PORT": {"eth0": {"mtu": "9000"}}}
        self.assertEqual(mod.add_missing_mgmt_ports(cfg), [])
        self.assertEqual(cfg["MGMT_PORT"], {"eth0": {"mtu": "9000"}})

    def test_one_port_for_several_addresses(self):
        cfg = {"MGMT_INTERFACE": {"eth0|10.1.1.1/24": {}, "eth0|fd00::1/64": {}}}
        self.assertEqual(mod.add_missing_mgmt_ports(cfg), ["eth0"])

    def test_names_outside_the_yang_pattern_are_ignored(self):
        cfg = {"MGMT_INTERFACE": {"mgmt0|10.1.1.1/24": {}, "eth01|10.2.2.2/24": {}}}
        self.assertEqual(mod.add_missing_mgmt_ports(cfg), [])
        self.assertNotIn("MGMT_PORT", cfg)

    def test_no_mgmt_interface_means_no_change(self):
        cfg = {"PORT": {}}
        self.assertEqual(mod.add_missing_mgmt_ports(cfg), [])
        self.assertEqual(cfg, {"PORT": {}})


class TestJmaCleanup(unittest.TestCase):

    def _yang_dir(self, with_model):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        if with_model:
            (Path(tmp.name) / mod.JMA_YANG).write_text("module sonic-dc-jma {}")
        return tmp.name

    def test_removes_jma_config_when_model_missing(self):
        cfg = json.loads(json.dumps(JMA_CONFIG))
        removed = mod.remove_jma_without_model(cfg, self._yang_dir(False))
        self.assertEqual(sorted(removed), sorted(
            ["DC_JMA", "FEATURE|dc-jma", "AUTO_TECHSUPPORT_FEATURE|dc-jma",
             "SYSLOG_CONFIG_FEATURE|dc-jma"]))
        self.assertEqual(cfg, {"FEATURE": {"swss": {"state": "enabled"}}})

    def test_keeps_jma_config_when_model_is_installed(self):
        cfg = json.loads(json.dumps(JMA_CONFIG))
        self.assertEqual(mod.remove_jma_without_model(cfg, self._yang_dir(True)), [])
        self.assertEqual(cfg, JMA_CONFIG)

    def test_feature_table_survives_when_it_becomes_empty(self):
        cfg = {"FEATURE": {"dc-jma": {"state": "enabled"}}}
        mod.remove_jma_without_model(cfg, self._yang_dir(False))
        self.assertEqual(cfg, {"FEATURE": {}})


class TestMigrateFile(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.cfg_path = self.dir / "config_db.json"
        self.yang = self.dir / "yang"
        self.yang.mkdir()

    def _write(self, cfg):
        self.cfg_path.write_text(json.dumps(cfg))
        os.chmod(self.cfg_path, 0o640)

    def test_repairs_file_and_keeps_a_backup_and_the_mode(self):
        original = dict(JMA_CONFIG, MGMT_INTERFACE={"eth0|10.1.1.1/24": {}})
        self._write(original)
        changes = mod.migrate(str(self.cfg_path), str(self.yang))
        self.assertIn("added MGMT_PORT|eth0", changes)
        self.assertIn("removed DC_JMA", changes)
        result = json.loads(self.cfg_path.read_text())
        self.assertNotIn("DC_JMA", result)
        self.assertEqual(result["MGMT_PORT"], {"eth0": {"admin_status": "up"}})
        self.assertEqual(self.cfg_path.stat().st_mode & 0o777, 0o640)
        backup = Path(str(self.cfg_path) + ".pre-juniper-migration")
        self.assertEqual(json.loads(backup.read_text()), original)

    def test_second_run_changes_nothing(self):
        self._write(dict(JMA_CONFIG, MGMT_INTERFACE={"eth0|10.1.1.1/24": {}}))
        mod.migrate(str(self.cfg_path), str(self.yang))
        before = self.cfg_path.read_text()
        self.assertEqual(mod.migrate(str(self.cfg_path), str(self.yang)), [])
        self.assertEqual(self.cfg_path.read_text(), before)

    def test_clean_config_is_not_rewritten_and_has_no_backup(self):
        self._write({"PORT": {"Ethernet0": {}}})
        before = self.cfg_path.read_text()
        self.assertEqual(mod.migrate(str(self.cfg_path), str(self.yang)), [])
        self.assertEqual(self.cfg_path.read_text(), before)
        self.assertFalse(Path(str(self.cfg_path) + ".pre-juniper-migration").exists())

    def test_main_never_fails_the_boot(self):
        self.assertEqual(mod.main([str(self.dir / "absent.json")]), 0)
        self.cfg_path.write_text("{not json")
        self.assertEqual(mod.main([str(self.cfg_path), "--yang-dir", str(self.yang)]), 0)
        self.assertEqual(self.cfg_path.read_text(), "{not json")


class TestHook(unittest.TestCase):
    """The hook is sourced by config-setup's run_hook() from inside a function."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.cfg = self.dir / "config_db.json"
        (self.dir / "yang").mkdir()

    def _source(self, script):
        env = dict(os.environ, CONFIG_DB_JSON=str(self.cfg),
                   JUNIPER_CONFIG_MIGRATE=str(script),
                   JUNIPER_YANG_DIR=str(self.dir / "yang"))
        return subprocess.run(
            ["bash", "-c", 'f() { . "$1"; }; f "$1"; echo "rc=$?"', "bash", str(HOOK)],
            env=env, capture_output=True, text=True, check=False)

    def test_sourcing_repairs_the_config_and_returns_zero(self):
        self.cfg.write_text(json.dumps(
            dict(JMA_CONFIG, MGMT_INTERFACE={"eth0|10.1.1.1/24": {}})))
        result = self._source(SCRIPT)
        self.assertIn("rc=0", result.stdout)
        repaired = json.loads(self.cfg.read_text())
        self.assertNotIn("DC_JMA", repaired)
        self.assertIn("eth0", repaired["MGMT_PORT"])

    def test_missing_script_is_skipped_without_error(self):
        original = json.dumps(JMA_CONFIG)
        self.cfg.write_text(original)
        result = self._source(self.dir / "not-installed.py")
        self.assertIn("rc=0", result.stdout)
        self.assertEqual(self.cfg.read_text(), original)

    def test_hook_name_is_listed_by_run_parts(self):
        self.assertRegex(HOOK.name, r"^[A-Za-z0-9_-]+$")

    def test_hook_has_valid_bash_syntax(self):
        subprocess.run(["bash", "-n", str(HOOK)], check=True)


class TestPackaging(unittest.TestCase):

    def test_manifest_installs_script_and_hook(self):
        manifest = (BASE_DIR / "debian" / "sonic-platform-juniper-common.install").read_text()
        self.assertIn("common/utils/juniper_config_migrate.py usr/local/bin", manifest)
        self.assertIn(
            "common/config-setup/70-juniper-config-migration "
            "etc/config-setup/config-migration-post-hooks.d/", manifest)

    def test_script_and_hook_are_executable_like_other_hooks(self):
        for path in (SCRIPT, HOOK):
            self.assertTrue(os.access(path, os.X_OK), path.name)


if __name__ == "__main__":
    unittest.main()
