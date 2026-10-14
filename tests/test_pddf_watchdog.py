"""Unit tests for sonic_platform_pddf/sonic_platform/watchdog.py"""

import unittest
from unittest import mock

from tests.conftest import stub_sonic_platform_pddf_base, SONIC_PLATFORM_PDDF_DIR, load_module

stub_sonic_platform_pddf_base()
mod = load_module("pddf_watchdog", SONIC_PLATFORM_PDDF_DIR / "watchdog.py")
impl_mod = load_module("pddf_watchdog_impl", SONIC_PLATFORM_PDDF_DIR / "impl_base" / "watchdog.py")

# Watchdog.__init__ does `from sonic_platform.override import load_impl`; stub it
# so construction wires the test's impl_mod copy instead of the real package.
import sys as _sys
import types as _types
_sys.modules.setdefault("sonic_platform", _types.ModuleType("sonic_platform"))
_override_stub = _types.ModuleType("sonic_platform.override")
_override_stub.load_impl = lambda kind, host=None: impl_mod.WatchdogImplBase(host)
_sys.modules["sonic_platform.override"] = _override_stub


class TestPddfWatchdog(unittest.TestCase):
    def _construct(self):
        """Build the facade via its real __init__ (load_impl stubbed to impl_mod)."""
        return mod.Watchdog()

    def _wire(self):
        """Facade with an impl attached but discovery not run."""
        w = mod.Watchdog.__new__(mod.Watchdog)
        w._impl = impl_mod.WatchdogImplBase(w)
        return w

    def _make_watchdog(self, state="active", timeout=45, identities=None):
        identities = identities or {
            "watchdog0": "unknown",
            "watchdog1": "HPE FPGA Watchdog",
        }

        def read_file(path):
            for dev, identity in identities.items():
                if path == "/sys/class/watchdog/{}/identity".format(dev):
                    return identity
            if path.endswith("/state"):
                return state
            if path.endswith("/timeout"):
                return str(timeout)
            return impl_mod.WDT_COMMON_ERROR

        patches = [
            mock.patch("os.listdir", return_value=sorted(identities.keys())),
            mock.patch.object(mod.Watchdog, "_read_file", side_effect=read_file, create=True),
            mock.patch.object(mod.Watchdog, "_gettimeout", return_value=timeout, create=True),
            mock.patch.object(mod.Watchdog, "_get_wdt", return_value=(object(), "watchdog1"), create=True),
            mock.patch.object(mod.Watchdog, "_disable", return_value=True, create=True),
            mock.patch.object(mod.Watchdog, "_gettimeleft", return_value=12, create=True),
        ]
        return patches

    def test_class_inherits_pddf(self):
        self.assertTrue(issubclass(mod.Watchdog, mod.PddfWatchdog))

    def test_instantiate(self):
        w = self._construct()
        self.assertIsNotNone(w)

    def test_selects_supported_watchdog_and_reads_state(self):
        patches = self._make_watchdog()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            w = self._construct()
            self.assertEqual(w.wdt_main_dev_name, "watchdog1")
            self.assertTrue(w.is_armed())
            self.assertEqual(w.timeout, 45)

    def test_falls_back_when_supported_watchdog_is_missing(self):
        # No watchdog with a supported identity — should fall back to PddfWatchdog
        # gracefully instead of raising, so pmon does not crash.
        patches = self._make_watchdog(identities={"watchdog0": "unknown"})
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            w = self._construct()  # must not raise
            self.assertIsNotNone(w)

    def test_falls_back_when_driver_watchdog_is_missing(self):
        # _get_wdt returns (None, None) — should fall back to PddfWatchdog
        # gracefully instead of raising.
        patches = self._make_watchdog()
        with patches[0], patches[1], patches[2], \
                mock.patch.object(mod.Watchdog, "_get_wdt", return_value=(None, None), create=True), \
                patches[4], patches[5]:
            w = self._construct()  # must not raise
            self.assertIsNotNone(w)

    def test_init_disables_watchdog_started_by_driver(self):
        wdt_object = object()
        with mock.patch.object(mod.Watchdog, "_get_wdt_main_dev_name", return_value="watchdog1", create=True), \
                mock.patch.object(mod.Watchdog, "_read_armed_state", side_effect=[False, True], create=True), \
                mock.patch.object(mod.Watchdog, "_read_file", return_value="active", create=True), \
                mock.patch.object(mod.Watchdog, "_gettimeout", return_value=45, create=True), \
                mock.patch.object(mod.Watchdog, "_get_wdt", return_value=(wdt_object, "watchdog1"), create=True), \
                mock.patch.object(mod.Watchdog, "_disable", return_value=True, create=True) as disable, \
                mock.patch.object(mod.Watchdog, "_read_timeout", return_value=45, create=True):
            w = self._construct()

        disable.assert_called_once_with()
        self.assertFalse(w.armed)

    def test_timeout_falls_back_to_sysfs_value(self):
        w = self._wire()
        w.timeout_path = "/sys/class/watchdog/watchdog1/timeout"

        with mock.patch.object(w, "_gettimeout", side_effect=Exception, create=True), \
                mock.patch.object(w, "_read_file", return_value="77", create=True):
            self.assertEqual(w._read_timeout(), 77)

    def test_timeout_uses_default_for_invalid_sysfs_value(self):
        w = self._wire()
        w.timeout_path = "/sys/class/watchdog/watchdog1/timeout"

        with mock.patch.object(w, "_gettimeout", side_effect=Exception, create=True), \
                mock.patch.object(w, "_read_file", return_value="invalid", create=True):
            self.assertEqual(w._read_timeout(), impl_mod.DEFAULT_TIMEOUT)

    def test_read_armed_state_handles_all_sysfs_values(self):
        w = self._wire()
        w.state_path = "/sys/class/watchdog/watchdog1/state"

        for state, expected in (
                (impl_mod.WDT_COMMON_ERROR, None),
                ("running", True),
                ("stopped", False),
                ("unknown", None)):
            with mock.patch.object(w, "_read_file", return_value=state, create=True):
                self.assertEqual(w._read_armed_state(), expected)

    def test_disarm_returns_true_when_state_stops(self):
        w = self._wire()
        w.armed = True

        with mock.patch.object(w, "_disable", return_value=True, create=True), \
                mock.patch.object(w, "_read_armed_state", return_value=False, create=True):
            self.assertTrue(w.disarm())

        self.assertFalse(w.armed)

    def test_disarm_returns_false_on_driver_error(self):
        w = self._wire()
        w.armed = True

        with mock.patch.object(w, "_disable", side_effect=IOError, create=True):
            self.assertFalse(w.disarm())

    def test_remaining_time_returns_error_when_disarmed(self):
        w = self._wire()
        w.armed = False

        with mock.patch.object(w, "_read_armed_state", return_value=False, create=True), \
                mock.patch.object(w, "_gettimeleft", return_value=12, create=True) as gettimeleft:
            self.assertEqual(w.get_remaining_time(), impl_mod.WDT_COMMON_ERROR)

        gettimeleft.assert_not_called()

    def test_remaining_time_returns_driver_value_when_armed(self):
        w = self._wire()
        w.armed = True

        with mock.patch.object(w, "_read_armed_state", return_value=True, create=True), \
                mock.patch.object(w, "_gettimeleft", return_value=12, create=True):
            self.assertEqual(w.get_remaining_time(), 12)

    def test_remaining_time_returns_error_on_driver_error(self):
        w = self._wire()
        w.armed = True

        with mock.patch.object(w, "_read_armed_state", return_value=True, create=True), \
                mock.patch.object(w, "_gettimeleft", side_effect=IOError, create=True):
            self.assertEqual(w.get_remaining_time(), impl_mod.WDT_COMMON_ERROR)


if __name__ == "__main__":
    unittest.main()


if __name__ == "__main__":
    unittest.main()
