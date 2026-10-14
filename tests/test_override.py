"""Unit tests for sonic_platform/override.py per-platform override loader."""

from tests.conftest import SONIC_PLATFORM_DIR, load_module

override = load_module("sp_override", SONIC_PLATFORM_DIR / "override.py")


def test_snake_mapping():
    assert override._snake("Sfp") == "sfp"
    assert override._snake("AsicThermal") == "asic_thermal"
    assert override._snake("VoltageSensor") == "voltage_sensor"


def test_no_impl_dir_returns_none(monkeypatch):
    monkeypatch.setattr(override, "_impl_dir", lambda: None)
    override._override_class.cache_clear()
    assert override._override_class("Sfp") is None


def test_loads_per_class_file(tmp_path, monkeypatch):
    (tmp_path / "sfp.py").write_text(
        "class Sfp:\n"
        "    def __init__(self, host=None):\n"
        "        self.host = host\n")
    monkeypatch.setattr(override, "_impl_dir", lambda: str(tmp_path))
    override._override_class.cache_clear()
    host = object()
    inst = override.load_impl("Sfp", host)
    assert type(inst).__name__ == "Sfp"
    assert inst.host is host


def test_lowercase_filename_fallback(tmp_path, monkeypatch):
    # snake_case of FwComponent is fw_component.py; author used fwcomponent.py
    (tmp_path / "fwcomponent.py").write_text(
        "class FwComponent:\n"
        "    def __init__(self, host=None):\n"
        "        pass\n")
    monkeypatch.setattr(override, "_impl_dir", lambda: str(tmp_path))
    override._override_class.cache_clear()
    assert override._override_class("FwComponent").__name__ == "FwComponent"


def test_missing_kind_file_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(override, "_impl_dir", lambda: str(tmp_path))
    override._override_class.cache_clear()
    assert override._override_class("Psu") is None
