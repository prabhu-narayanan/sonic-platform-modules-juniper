"""Unit tests for qfx5241/utils/qfx5241_pre_device_create.py.

The CPU SMBus (i2c-0) is the parent of the PCA9548 muxes, and the I2C core
rejects a mux-channel client whose address a parent-bus client already holds.
ee1004 holds 0x36/0x37 there, which blocks VRM5 (0x36), so the hook unbinds it.
"""

import unittest
from unittest import mock

from tests.conftest import (BASE_DIR, stub_sonic_py_common, stub_syslog,
                            load_module)

stub_syslog()
stub_sonic_py_common()

mod = load_module("qfx5241_pre_device_create",
                  BASE_DIR / "qfx5241" / "utils" / "qfx5241_pre_device_create.py")


class TestUnbindEe1004(unittest.TestCase):

    def _driver_dir(self, tmp_path, clients):
        for name in clients + ["bind", "uevent", "module"]:
            (tmp_path / name).write_text("")
        return str(tmp_path)

    def test_unbinds_cpu_smbus_client(self, ):
        import tempfile
        import pathlib
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            driver_dir = self._driver_dir(tmp_path, ["0-0051"])
            with mock.patch.object(mod, "log_info"):
                unbound = mod.unbind_ee1004_from_cpu_smbus(driver_dir)
            self.assertEqual(unbound, ["0-0051"])
            self.assertEqual((tmp_path / "unbind").read_text(), "0-0051")

    def test_ignores_clients_on_other_buses_and_driver_files(self):
        import tempfile
        import pathlib
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            driver_dir = self._driver_dir(tmp_path, ["33-0051", "21-0036"])
            with mock.patch.object(mod, "log_info"):
                self.assertEqual(mod.unbind_ee1004_from_cpu_smbus(driver_dir), [])
            self.assertFalse((tmp_path / "unbind").exists())

    def test_every_cpu_smbus_client_is_unbound(self):
        writes = []
        handle = mock.mock_open()
        handle.return_value.write.side_effect = writes.append
        with mock.patch.object(mod.os, "listdir", return_value=["0-0050", "0-0051", "bind"]), \
                mock.patch("builtins.open", handle), \
                mock.patch.object(mod, "log_info"):
            unbound = mod.unbind_ee1004_from_cpu_smbus("/x")
        self.assertEqual(unbound, ["0-0050", "0-0051"])
        self.assertEqual(writes, ["0-0050", "0-0051"])

    def test_driver_not_loaded_is_not_an_error(self):
        with mock.patch.object(mod.os, "listdir", side_effect=FileNotFoundError):
            self.assertEqual(mod.unbind_ee1004_from_cpu_smbus("/x"), [])

    def test_failed_unbind_is_logged_and_skipped(self):
        with mock.patch.object(mod.os, "listdir", return_value=["0-0051"]), \
                mock.patch("builtins.open", side_effect=OSError("busy")), \
                mock.patch.object(mod, "log_warning") as warn, \
                mock.patch.object(mod, "log_info") as info:
            self.assertEqual(mod.unbind_ee1004_from_cpu_smbus("/x"), [])
        warn.assert_called_once()
        info.assert_not_called()


class TestPackaging(unittest.TestCase):

    def test_dispatcher_routes_qfx5241(self):
        script = (BASE_DIR / "common" / "utils" / "pddf_pre_device_create.sh").read_text()
        self.assertIn("x86_64-juniper_qfx5241-r0)", script)
        self.assertIn("/usr/local/bin/qfx5241_pre_device_create.py", script)

    def test_manifest_installs_hook_and_blacklist(self):
        manifest = (BASE_DIR / "debian" / "sonic-platform-juniper-qfx5241.install").read_text()
        self.assertIn("qfx5241/utils/qfx5241_pre_device_create.py usr/local/bin", manifest)
        self.assertIn("qfx5241/conf/blacklist-ee1004.conf etc/modprobe.d/", manifest)

    def test_blacklist_file_blocks_ee1004_alias_loading(self):
        conf = (BASE_DIR / "qfx5241" / "conf" / "blacklist-ee1004.conf").read_text()
        active = [line.strip() for line in conf.splitlines()
                  if line.strip() and not line.lstrip().startswith("#")]
        self.assertEqual(active, ["blacklist ee1004"])


if __name__ == "__main__":
    unittest.main()
