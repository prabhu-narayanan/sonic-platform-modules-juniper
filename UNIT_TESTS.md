# Unit Test Scripts — platform/broadcom/sonic-platform-modules-juniper

All tests use Python's `unittest` framework and mock hardware interactions so they
can run in any CI environment without root or device access.

## Running Tests

```bash
cd platform/broadcom/sonic-platform-modules-juniper
python3 -m pytest tests/
```

To run a single test file:

```bash
python3 -m pytest tests/test_fan.py -vv
```

### Code Coverage

Coverage is configured automatically via `pytest.ini` using `pytest-cov`.
Running `pytest` produces:

| Output | Description |
|---|---|
| Terminal summary | Line-by-line coverage printed to stdout |
| `htmlcov/` | Interactive HTML coverage report |
| `coverage.xml` | Cobertura XML for CI integration |
| `test-results.xml` | JUnit XML test results |

To override the default `pytest.ini` settings:

```bash
python3 -m pytest tests/ --cov=sonic_platform --cov=sonic_platform_pddf --cov-report term --cov-report html --junitxml=test-results.xml
```

During the image build, `pytest` runs automatically (with coverage) unless
`SKIP_PLATFORM_TEST=y` is set.

### During Image Build

Unit tests run automatically during the `build` stage of the Debian package
build via `platform/broadcom/sonic-platform-modules-juniper/debian/rules`.

To **skip** tests during the build, set the environment variable:

```bash
SKIP_PLATFORM_TEST=y make target/sonic-broadcom.bin
```

---

Tests live in `tests/`. Shared helpers and base class stubs are in
`tests/conftest.py`.

## sonic\_platform Modules

| Test File | Script Under Test | Tests | Description |
|---|---|---|---|
| `tests/test_fan.py` | `sonic_platform/fan.py` | 13 | Fan name/model/direction, speed tolerance, delegation to inventory object |
| `tests/test_fan_drawer.py` | `sonic_platform/fan_drawer.py` | 9 | Fan drawer name/position/presence, delegation to slot object |
| `tests/test_psu.py` | `sonic_platform/psu.py` | 15 | PSU voltage/current/power, presence/status, LED control, master LED class methods |
| `tests/test_thermal.py` | `sonic_platform/thermal.py` | 21 | Thermal name (sensor/SFP), EM policy thresholds (WTC/WT/HT/YAT/RAT/FT), temperature reading, min/max tracking |
| `tests/test_fwcomponent.py` | `sonic_platform/fwcomponent.py` | 14 | Firmware component name/version/install, presence logic, auto\_update |
| `tests/test_ssd.py` | `sonic_platform/ssd.py` | 4 | SSD init, model extraction from smartctl output, error handling |
| `tests/test_sensor.py` | `sonic_platform/sensor.py` | 14 | Voltage sensor name/thresholds, set\_threshold raises, presence/status |
| `tests/test_watchdog.py` | `sonic_platform/watchdog.py` | 5 | Watchdog arm/disarm/is\_armed state machine, remaining time |
| `tests/test_eeprom.py` | `sonic_platform/eeprom.py` | 4 | EEPROM constants, class existence, accessor method signatures |
| `tests/test_thermal_manager.py` | `sonic_platform/thermal_manager.py` | 2 | ThermalManager poll interval constant |
| `tests/test_thermal_conditions.py` | `sonic_platform/thermal_conditions.py` | 8 | Fan/Thermal/PSU condition matching (presence, absence, critical threshold) |
| `tests/test_thermal_actions.py` | `sonic_platform/thermal_actions.py` | 7 | SetFanSpeedAction JSON loading, speed validation, fan speed dispatch |

## sonic\_platform\_pddf Modules

| Test File | Script Under Test | Tests | Description |
|---|---|---|---|
| `tests/test_pddf_component.py` | `sonic_platform_pddf/.../component.py` | 7 | Firmware update notification — cold/warm/fast reboot, None/invalid |
| `tests/test_pddf_thermal.py` | `sonic_platform_pddf/.../thermal.py` | 8 | JSON dev\_attr threshold getters, name override, critical threshold fallback |
| `tests/test_pddf_voltage_sensor.py` | `sonic_platform_pddf/.../voltage_sensor.py` | 2 | I2C bus MUX delegation, class inheritance |
| `tests/test_pddf_watchdog.py` | `sonic_platform_pddf/.../watchdog.py` | 2 | Class inheritance, instantiation |
| `tests/test_pddf_thermal_manager.py` | `sonic_platform_pddf/.../thermal_manager.py` | 3 | Poll interval from JSON, default fallback, caching |

## Platform Utils

| Test File | Script Under Test | Tests | Description |
|---|---|---|---|
| `tests/test_qfx5140_platform_init.py` | `qfx5140/utils/platform_init.py` | 10 | GPIO chip base lookup, pin read, gpio\_control (high/low/out/in), run\_cmd, log\_os\_system |

**Total: 154 tests (all passing)**
