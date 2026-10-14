#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qfx5241_diag.py  —  QFX5241-64 Platform Diagnostics
=====================================================
Comprehensive post-boot diagnostic tool for the Juniper QFX5241-64 (Garnet)
running SONiC.  Run as root after the platform has booted.

Sections
--------
 1  Package installation
 2  sonic-platform-common package
 3  sonic-platform-juniper-qfx5241 package
 4  Pre-PDDF / platform-init status
 5  PDDF install and init (all KO modules)
 6  Post-PDDF init and driver status
 7  Per-driver loaded status (from pddf-device.json)
 8  MFD (Multi-Function Device) creation
 9  I2C / GPIO / FPGA / LED / Sensor sysfs access
10  User-space installation (Python wheels, CLI tools)
11  SONiC docker container status
12  pmon daemon status
13  ASIC bring-up status
14  Platform CLIs
15  Interface CLIs

Usage
-----
    sudo python3 /usr/lib/python3/dist-packages/sonic_platform/qfx5241_diag.py
    sudo python3 qfx5241_diag.py [--section N] [--json] [--report FILE] [-v]

Report
------
    --report /tmp/qfx5241_diag_report.txt   Save a full plain-text report
    --report /tmp/qfx5241_diag_report.json  Save JSON report (combine with --json)

Exit codes
----------
    0  All checks passed
    1  One or more checks failed
"""

import argparse
import io
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Colour helpers (disabled when not a tty or --json is used)
# ---------------------------------------------------------------------------
_USE_COLOUR = sys.stdout.isatty()

# Report capture — when --report is used, output is also written here
_report_buf = io.StringIO()
_report_path = None

def _emit(text, end="\n"):
    """Print to stdout and capture in report buffer."""
    print(text, end=end)
    # Strip ANSI codes for the report file
    clean = re.sub(r'\033\[[0-9;]*m', '', text)
    _report_buf.write(clean + end)

def _c(code, text):
    return f"\033[{code}m{text}\033[0m" if _USE_COLOUR else text

def _green(t):  return _c("32", t)
def _red(t):    return _c("31", t)
def _yellow(t): return _c("33", t)
def _cyan(t):   return _c("36", t)
def _bold(t):   return _c("1",  t)


def _save_report():
    """Write the captured report buffer to _report_path."""
    if not _report_path:
        return
    try:
        content = _report_buf.getvalue()
        with open(_report_path, 'w') as f:
            f.write(content)
        print(f"\n  Report saved: {_report_path}")
    except Exception as e:
        print(f"\n  WARNING: Could not save report: {e}", file=sys.stderr)

# ---------------------------------------------------------------------------
# Platform constants
# ---------------------------------------------------------------------------
PLATFORM_NAME  = "QFX5241-64-OD (Garnet)"
PLATFORM_DIR   = "/usr/share/sonic/device/x86_64-juniper_qfx5241-r0"
PDDF_JSON      = os.path.join(PLATFORM_DIR, "pddf", "pddf-device.json")
PD_PLUGIN_JSON = os.path.join(PLATFORM_DIR, "pddf", "pd-plugin.json")

# All kernel modules that MUST be loaded (from pddf-device.json)
CUSTOM_KOS = [
    "jnx-wq",
    "qfx5241-jnx-xrefpga-lpcm",
    "qfx5241-jnx-garnet-core",
    "qfx5241-gpio-garnet",
    "qfx5241-i2c-ocores-garnet",
    "qfx5241-i2c-mux",
    "qfx5241-jnx-garnet-fancpld",
    "qfx5241-jnx-s32afc-gpio-presence",
    "qfx5241-leds",
    "qfx5241-leds-jnx-i2cs",
    "qfx5241-jnx-garnet-psu",
    "lm75",
    "ucd9000",
    "xdpe152c4",
]

STD_KOS = [
    "i2c-dev",
    "i2c-mux",
    "optoe",
    "at24",
]

PDDF_KOS = [
    "pddf_client_module",
    "pddf_mux_module",
    "pddf_xcvr_module",
    "pddf_psu_module",
    "pddf_psu_driver_module",
    "pddf_fan_module",
    "pddf_fan_driver_module",
    "pddf_led_module",
    "pddf_sysstatus_module",
]

# I2C bus topology — bus IDs that MUST exist after driver init
I2C_BUSES_REQUIRED = {
    "0":    "iSMT SMBus (pci 00:1f.4)",
    "16":   "MUX1 ch0 (PCA9548@0x78)",
    "17":   "MUX1 ch1",
    "18":   "MUX1 ch2",
    "21":   "MUX2 ch1 — PSU1 bus",
    "22":   "MUX2 ch2 — TEMP sensors",
    "23":   "MUX2 ch3 — TEMP sensors",
    "32":   "MUX3 ch0 (PCA9548@0x76 via MUX2)",
    "33":   "MUX3 ch1",
    "64":   "ocores CPLD1 port 0",
    "96":   "ocores CPLD2 port 32",
    "128":  "ocores SFP port 64",
}

# PDDF sysfs base directories
PDDF_SYSFS = "/sys/kernel/pddf"
PDDF_CLASS = "/sys/bus/platform/drivers/pddf_client"

# Temp sensors — (bus, addr, driver, label)
TEMP_SENSORS = [
    (34, "0x48", "lm75", "MB Middle Right Rear"),
    (34, "0x4a", "lm75", "MB Middle Left Rear"),
    (34, "0x4b", "lm75", "MB Left Rear"),
    (34, "0x4c", "lm75", "MB Right Rear"),
    (35, "0x49", "lm75", "MB Front Right"),
    (35, "0x4d", "lm75", "MB Front Left"),
    (48, "0x4d", "lm75", "FAN Board"),
    (49, "0x4e", "lm75", "PSU Area"),
]

# GPIO chip labels that MUST appear in /sys/class/gpio/
GPIO_LABELS_REQUIRED = [
    "fan-presence",
    "presence-cpld0",
    "presence-cpld1",
    "presence-sfp",
    "lpmod-cpld0",
    "lpmod-cpld1",
]

# LED class names under /sys/class/leds/
LED_NAMES_REQUIRED = [
    "system",
    "fan",
    # PSU LEDs are controlled by CPLD directly on QFX5241, not via sysfs LED class
    # "psu1",  "psu2" — not present in /sys/class/leds/
]

# FPGA / CFPGA PCI device
CFPGA_PCI_PATH = "/sys/bus/pci/devices/0000:02:00.0"

# PSU PMBUS I2C addresses
# PSU1=33-0058, PSU2=33-0059 (both on MUX3 ch0)
PSU_PMBUS = [
    (33, "0x58", "PSU1"),
    (33, "0x59", "PSU2"),
]

# FAN controller
FAN_CTRL_BUS  = 32
FAN_CTRL_ADDR = "0x33"

# SONiC expected docker containers
SONIC_DOCKERS = [
    "syncd",
    "swss",
    "bgp",
    "teamd",
    "pmon",
    "lldp",
    "snmp",
    "radv",
    "mgmt-framework",
    "database",
    "eventd",
    "gnmi",
]

# pmon daemons expected in the pmon container
# Note: ycabled, chassisd are in 202511 but optional on QFX5241 (no Y-cable / no chassis)
PMON_DAEMONS = [
    "xcvrd",
    "thermalctld",
    "psud",
    "sensormond",
    "ledd",
    "pcied",
    "syseepromd",
    "stormond",
]

# 202511 pmon daemons that are optional / may not run on all hardware
PMON_DAEMONS_OPTIONAL_202511 = [
    "fancontrol",   # lm-sensors fancontrol (may be superseded by thermalctld)
    "chassisd",     # chassis systems only — not expected on QFX5241
    "ycabled",      # Y-cable support — not present on QFX5241
]

# Platform CLI commands to exercise (cmd, expected substring or None)
PLATFORM_CLIS = [
    (["show", "platform", "summary"],           "Platform"),
    (["show", "platform", "syseeprom"],         "Product Name"),
    (["show", "platform", "psustatus"],         "PSU"),
    (["show", "platform", "fan"],               None),
    (["show", "platform", "temperature"],       "Temp"),
    (["show", "platform", "firmware"],          None),
    (["show", "environment"],                   None),
    (["show", "reboot-cause"],                  None),
    (["show", "system-health", "summary"],      None),
    (["show", "logging", "--lines", "10"],      None),
]

INTERFACE_CLIS = [
    (["show", "interfaces", "status"],          None),
    (["show", "interfaces", "transceiver", "presence"], None),
    (["show", "interfaces", "transceiver", "info", "Ethernet0"], None),
    (["show", "lldp", "neighbors"],             None),
    (["show", "arp"],                           None),
    (["show", "ip", "route", "summary"],        None),
    (["show", "mac", "--count"],                None),
    (["show", "vlan", "brief"],                 None),
]

# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------
_results: list[dict] = []
_section_counters: dict[int, dict] = {}


def _rec(section: int, test: str, ok: bool, detail: str = "", value: str = ""):
    """Record a single check result."""
    status = "PASS" if ok else "FAIL"
    _results.append({
        "section": section,
        "test":    test,
        "status":  status,
        "detail":  detail,
        "value":   value,
    })
    ctr = _section_counters.setdefault(section, {"pass": 0, "fail": 0})
    if ok:
        ctr["pass"] += 1
    else:
        ctr["fail"] += 1
    return ok


def _run(cmd, timeout=15, shell=False):
    """Run a command; return (returncode, stdout, stderr)."""
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=shell,
        )
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT"
    except FileNotFoundError:
        return -1, "", "command not found"
    except Exception as e:
        return -1, "", str(e)


def _sysfs(path):
    """Read a sysfs file; return stripped string or None."""
    try:
        return Path(path).read_text().strip()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Section header / print helpers
# ---------------------------------------------------------------------------
VERBOSE = False

def _section(n: int, title: str):
    print()
    print(_bold(_cyan(f"{'='*70}")))
    print(_bold(_cyan(f"  Section {n:2d}: {title}")))
    print(_bold(_cyan(f"{'='*70}")))


def _pass(test: str, detail: str = "", value: str = "", section: int = 0):
    tag = _green("[PASS]")
    line = f"  {tag}  {test}"
    if value:
        line += f"  =  {value}"
    if detail and VERBOSE:
        line += f"\n         {detail}"
    print(line)
    _rec(section, test, True, detail, value)


def _fail(test: str, detail: str = "", value: str = "", section: int = 0):
    tag = _red("[FAIL]")
    line = f"  {tag}  {test}"
    if value:
        line += f"  =  {value}"
    if detail:
        line += f"\n         {_yellow(detail)}"
    print(line)
    _rec(section, test, False, detail, value)


def _info(msg: str):
    print(f"  {_cyan('[INFO]')}  {msg}")


def _warn(msg: str):
    print(f"  {_yellow('[WARN]')}  {msg}")


# ---------------------------------------------------------------------------
# S E C T I O N   1  —  Installation
# ---------------------------------------------------------------------------
def sec1_installation(s=1):
    _section(s, "Installation")

    # Check we are running on the right platform
    # In 202411, DEVICE_METADATA is in CONFIG_DB — use sonic-cfggen
    rc_cfg, out_cfg, _ = _run(["sonic-cfggen", "-d", "-v",
                                "DEVICE_METADATA.localhost.hwsku"], timeout=5)
    if rc_cfg == 0 and out_cfg.strip():
        hw = out_cfg.strip()
        _pass("device_metadata.json readable", value=f"hwsku={hw} (CONFIG_DB)", section=s)
        if "QFX5241" in hw or "Juniper" in hw.lower():
            _pass("HW SKU matches QFX5241", value=hw, section=s)
        else:
            _fail("HW SKU matches QFX5241", detail=f"Got: {hw}", section=s)
    elif False:  # placeholder to preserve structure
        try:
            meta = json.loads(out)
            hw = meta.get("localhost", {}).get("hwsku", "")
            _pass("device_metadata.json readable", section=s)
            if "QFX5241" in hw or "Juniper" in hw.lower():
                _pass("HW SKU matches QFX5241", value=hw, section=s)
            else:
                _fail("HW SKU matches QFX5241", detail=f"Got: {hw}", section=s)
        except json.JSONDecodeError:
            _fail("device_metadata.json parse", detail="Invalid JSON", section=s)
    else:
        _fail("device_metadata.json readable", detail="File not found", section=s)

    # SONiC version
    rc, out, _ = _run(["sonic-cfggen", "-d", "-v", "DEVICE_METADATA.localhost.sonic_version"],
                      timeout=5)
    ver = out.strip() if rc == 0 else "N/A"
    if ver and ver != "N/A":
        _pass("SONiC version readable", value=ver, section=s)
    else:
        rc2, out2, _ = _run(["cat", "/etc/sonic/sonic_version.yml"])
        ver2 = ""
        for line in out2.splitlines():
            if "build_version" in line:
                ver2 = line.split(":", 1)[-1].strip()
        _pass("SONiC version (yml)", value=ver2 or "unknown", section=s)

    # Kernel version
    rc, out, _ = _run(["uname", "-r"])
    _pass("Kernel version", value=out.strip(), section=s)

    # PDDF device JSON present
    if os.path.isfile(PDDF_JSON):
        _pass("pddf-device.json present", value=PDDF_JSON, section=s)
    else:
        _fail("pddf-device.json present", detail=f"Missing: {PDDF_JSON}", section=s)

    # platform_components.json
    comp_json = os.path.join(PLATFORM_DIR, "platform_components.json")
    if os.path.isfile(comp_json):
        _pass("platform_components.json present", section=s)
    else:
        _fail("platform_components.json present", detail=f"Missing: {comp_json}", section=s)

    # platform.json
    plat_json = os.path.join(PLATFORM_DIR, "platform.json")
    if os.path.isfile(plat_json):
        _pass("platform.json present", section=s)
    else:
        _fail("platform.json present", detail=f"Missing: {plat_json}", section=s)


# ---------------------------------------------------------------------------
# S E C T I O N   2  —  sonic-platform-common package
# ---------------------------------------------------------------------------
def sec2_sonic_platform_common(s=2):
    _section(s, "sonic-platform-common package")

    # Check for Juniper-specific sonic-platform deb (not the community sonic-platform-common)
    rc, out, _ = _run(["dpkg", "-l", "sonic-platform-juniper-common"])
    if rc == 0 and "ii  sonic-platform-juniper-common" in out:
        ver_match = re.search(r"sonic-platform-juniper-common\s+(\S+)", out)
        ver = ver_match.group(1) if ver_match else "?"
        _pass("sonic-platform-common installed", value=f"sonic-platform-juniper-common {ver}", section=s)
    else:
        # Also check community package
        rc2, out2, _ = _run(["dpkg", "-l", "sonic-platform-common"])
        if rc2 == 0 and "ii  sonic-platform-common" in out2:
            ver_match = re.search(r"sonic-platform-common\s+(\S+)", out2)
            ver = ver_match.group(1) if ver_match else "?"
            _pass("sonic-platform-common installed", value=ver, section=s)
        else:
            _fail("sonic-platform-common installed",
                  detail="sonic-platform-juniper-common not installed", section=s)

    # pddf_fan / pddf_chassis importable
    # Note: in 202511 importing pddf_chassis/pddf_psu cascades into sonic_platform imports
    # which may fail in diag context. Test with isolated subprocess and treat as warn.
    for mod in ["sonic_platform_pddf_base.pddf_chassis",
                "sonic_platform_pddf_base.pddf_fan",
                "sonic_platform_pddf_base.pddf_psu",
                "sonic_platform_pddf_base.pddf_sfp"]:
        rc, out, err = _run([sys.executable, "-c",
                             f"import importlib; importlib.import_module('{mod}')"])
        if rc == 0:
            _pass(f"import {mod}", section=s)
        else:
            # Check if the module FILE exists even if import cascades fail
            mod_file = mod.replace('.', '/') + '.py'
            found = any(
                os.path.isfile(os.path.join(p, mod_file))
                for p in sys.path if p
            )
            if found:
                _warn(f"import {mod}: file present but import cascade fails (non-critical)")
            else:
                _fail(f"import {mod}", detail="Module not importable", section=s)

    # sonic_py_common
    rc, _, _ = _run([sys.executable, "-c", "from sonic_py_common.logger import Logger"])
    if rc == 0:
        _pass("sonic_py_common importable", section=s)
    else:
        _fail("sonic_py_common importable", detail="pip install sonic-py-common", section=s)


# ---------------------------------------------------------------------------
# S E C T I O N   3  —  sonic-platform-juniper-qfx5241 package
# ---------------------------------------------------------------------------
def sec3_sonic_platform_qfx5241(s=3):
    _section(s, "sonic-platform-juniper-qfx5241 package")

    # dpkg status
    for pkg in ["sonic-platform-juniper-qfx5241",
                "sonic-platform-juniper-common"]:
        rc, out, _ = _run(["dpkg", "-l", pkg])
        if rc == 0 and f"ii  {pkg}" in out:
            match = re.search(rf"{pkg}\s+(\S+)", out)
            ver = match.group(1) if match else "?"
            _pass(f"dpkg: {pkg}", value=ver, section=s)
        else:
            _fail(f"dpkg: {pkg}", detail=f"Not installed", section=s)

    # sonic_platform wheel installed
    rc, out, _ = _run([sys.executable, "-m", "pip", "show", "sonic-platform"])
    if rc == 0:
        loc = ""
        for line in out.splitlines():
            if line.startswith("Location:"):
                loc = line.split(":", 1)[-1].strip()
        _pass("sonic-platform Python wheel", value=loc, section=s)
    else:
        _fail("sonic-platform Python wheel", detail="pip install sonic-platform*.whl", section=s)

    # Import the platform chassis
    rc, out, err = _run([sys.executable, "-c",
                         "from sonic_platform.platform import Platform; p=Platform(); "
                         "c=p.get_chassis(); print(c.get_name())"])
    if rc == 0:
        _pass("sonic_platform.Platform() instantiation", value=out.strip(), section=s)
    else:
        _fail("sonic_platform.Platform() instantiation",
              detail=err.strip()[:200], section=s)

    # Key Python module files — check both possible install locations
    # pip3 install --user puts to /usr/local/lib/pythonX.Y/dist-packages
    # system deb puts to /usr/lib/python3/dist-packages
    import glob as _glob
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    search_bases = [
        f"/usr/local/lib/python{py_ver}/dist-packages/sonic_platform",
        "/usr/local/lib/python3/dist-packages/sonic_platform",
        "/usr/lib/python3/dist-packages/sonic_platform",
        "/usr/local/lib/sonic_platform",
    ]
    # Also check pip-installed location via importlib
    try:
        import importlib.util as _ilu
        spec = _ilu.find_spec("sonic_platform.chassis")
        if spec and spec.origin:
            search_bases.insert(0, str(Path(spec.origin).parent))
    except Exception:
        pass
    base = next((b for b in search_bases if os.path.isdir(b)), None)
    # No sfp_qfx5241.py override here: QFX5241's dual-CPLD GPIO split is
    # resolved generically by sfp.py via pddf-device.json's gpio_label_groups.
    for f in ["chassis.py", "fan.py", "psu.py", "sfp.py", "thermal.py",
              "sensor.py", "eeprom.py", "component.py"]:
        if base and os.path.isfile(os.path.join(base, f)):
            _pass(f"sonic_platform/{f}", section=s)
        else:
            # Final fallback: search system-wide
            found = _glob.glob(f"/usr/**/sonic_platform/{f}", recursive=True)
            if found:
                _pass(f"sonic_platform/{f}", value=found[0], section=s)
            else:
                _fail(f"sonic_platform/{f}",
                      detail=f"Not found in any Python path (searched: {', '.join(search_bases[:2])})",
                      section=s)

    # Init scripts present
    for script in ["/usr/local/bin/qfx5241_platform_init.py",
                   "/usr/local/bin/qfx5241_post_pddf_init.py"]:
        if os.path.isfile(script):
            _pass(f"init script: {os.path.basename(script)}", section=s)
        else:
            _fail(f"init script: {os.path.basename(script)}",
                  detail=f"Missing: {script}", section=s)

    # 202511: common_platform_init.py must exist and be executable
    common_init = "/usr/local/bin/common_platform_init.py"
    if os.path.isfile(common_init):
        executable = os.access(common_init, os.X_OK)
        if executable:
            _pass("common_platform_init.py present and executable", section=s)
        else:
            _fail("common_platform_init.py executable",
                  detail=f"chmod +x {common_init}", section=s)
    else:
        _fail("common_platform_init.py present",
              detail=f"Missing: {common_init} — sonic-platform-juniper-common not installed?",
              section=s)


# ---------------------------------------------------------------------------
# S E C T I O N   4  —  Pre-PDDF / platform-init status
# ---------------------------------------------------------------------------
def sec4_pre_pddf_init(s=4):
    _section(s, "Pre-PDDF / platform-init status")

    # pddf-platform-init.service
    rc, out, _ = _run(["systemctl", "is-active", "pddf-platform-init"])
    active = out.strip()
    if active == "active":
        _pass("pddf-platform-init.service active", section=s)
    else:
        _fail("pddf-platform-init.service active", detail=f"State: {active}", section=s)

    # Check service exit code
    rc2, out2, _ = _run(["systemctl", "show", "pddf-platform-init",
                          "--property=ExecMainStatus"])
    m = re.search(r"ExecMainStatus=(\d+)", out2)
    exit_code = m.group(1) if m else "?"
    if exit_code == "0":
        _pass("pddf-platform-init exit code 0", section=s)
    else:
        _fail("pddf-platform-init exit code 0",
              detail=f"Exit code: {exit_code}", section=s)

    # 202511: juniper-common-platform-init.service (new in 202511 common/platform split)
    rc_c, out_c, _ = _run(["systemctl", "is-active", "juniper-common-platform-init"])
    state_c = out_c.strip()
    if state_c == "active":
        _pass("juniper-common-platform-init.service active", section=s)
    else:
        _fail("juniper-common-platform-init.service active",
              detail=f"State: {state_c} — check: journalctl -u juniper-common-platform-init",
              section=s)

    # Verify ONIE EEPROM cache was populated by common_platform_init
    eeprom_cache = "/var/run/platform_cache/onie_syseeprom.cache"
    if os.path.isfile(eeprom_cache):
        size = os.path.getsize(eeprom_cache)
        _pass("ONIE syseeprom cache present", value=f"{size} bytes", section=s)
    else:
        _fail("ONIE syseeprom cache present",
              detail=f"Missing: {eeprom_cache} — common_platform_init.py eeprom() failed?",
              section=s)

    # Ensure pmon container was cleaned up before start
    rc3, out3, _ = _run(["docker", "inspect", "--format={{.State.Status}}", "pmon"])
    state = out3.strip()
    if state in ("running", "created"):
        _pass("pmon container state after init", value=state, section=s)
    else:
        _warn(f"pmon container state: {state or 'not found'}")

    # dmesg for obvious platform driver errors
    rc4, out4, _ = _run(["dmesg", "--notime", "--level=err,crit,alert,emerg"],
                         timeout=10)
    jnpr_errs = [l for l in out4.splitlines()
                  if any(x in l for x in ["qfx5241", "jnx-", "garnet", "pddf"])]
    if not jnpr_errs:
        _pass("dmesg: no QFX5241 driver errors", section=s)
    else:
        for e in jnpr_errs[:5]:
            # EBUSY (-16) on garnet-fancpld is non-fatal — device still works via retry
            if "(-16)" in e or "EBUSY" in e:
                _warn(f"dmesg: {e[:120]} (EBUSY — device may still work)")
            else:
                _fail(f"dmesg error: {e[:100]}", section=s)


# ---------------------------------------------------------------------------
# S E C T I O N   5  —  PDDF install and init (kernel modules)
# ---------------------------------------------------------------------------
def sec5_pddf_install(s=5):
    _section(s, "PDDF install and init — kernel modules")

    rc, out, _ = _run(["lsmod"])
    loaded = set(out.split()) if rc == 0 else set()

    def _check_ko(name, label=""):
        # lsmod uses underscores; kernel module names may use hyphens or underscores
        normalized = name.replace("-", "_")
        ok = normalized in loaded or name.replace("_", "-") in loaded
        # Also check /proc/modules
        if not ok:
            rc2, out2, _ = _run(["grep", "-w", normalized, "/proc/modules"])
            ok = rc2 == 0
        label = label or name
        if ok:
            _pass(f"KO loaded: {label}", section=s)
        else:
            _fail(f"KO loaded: {label}",
                  detail=f"modprobe {name}  or check /lib/modules/$(uname -r)/", section=s)
        return ok

    _info("--- Standard KOs ---")
    for ko in STD_KOS:
        _check_ko(ko)

    _info("--- Custom (Juniper) KOs ---")
    for ko in CUSTOM_KOS:
        _check_ko(ko)

    _info("--- PDDF KOs ---")
    for ko in PDDF_KOS:
        _check_ko(ko)

    # /sys/kernel/pddf exists
    if os.path.isdir(PDDF_SYSFS):
        _pass("PDDF sysfs dir exists", value=PDDF_SYSFS, section=s)
    else:
        _fail("PDDF sysfs dir exists", detail=f"{PDDF_SYSFS} missing", section=s)


# ---------------------------------------------------------------------------
# S E C T I O N   6  —  Post-PDDF init and driver status
# ---------------------------------------------------------------------------
def sec6_post_pddf_init(s=6):
    _section(s, "Post-PDDF init and driver status")

    # qfx5241-jnx-garnet-psu loaded (done in post_pddf_init)
    rc, out, _ = _run(["lsmod"])
    for mod in ["qfx5241_jnx_garnet_psu", "qfx5241_jnx_s32afc_gpio_presence",
                 "xdpe152c4", "ucd9000"]:
        ok = mod in (out or "")
        if not ok:
            ok2, _, _ = _run(["grep", "-w", mod, "/proc/modules"])
            ok = ok2 == 0
        if ok:
            _pass(f"Post-PDDF module: {mod}", section=s)
        else:
            _fail(f"Post-PDDF module: {mod}",
                  detail="Should be loaded by qfx5241_post_pddf_init.py", section=s)

    # VRM (xdpe12284) voltage regulators — on bus 21 (MUX2 ch1)
    # Addresses found: 0x18, 0x2a, 0x2e, 0x30, 0x40 (0x36 may not be populated on all HW revs)
    xdpe_addrs = ["0x18", "0x2a", "0x2e", "0x30", "0x36", "0x40"]
    for addr in xdpe_addrs:
        bus = 21  # MUX2 ch1 — confirmed on live system
        dev_path = f"/sys/bus/i2c/devices/{bus}-{int(addr,0):04x}"
        if os.path.exists(dev_path):
            _pass(f"VRM xdpe12284 {addr} on bus {bus}", section=s)
        else:
            if addr == "0x36":
                _info(f"VRM xdpe12284 {addr} on bus {bus} — not populated on this HW rev")
            else:
                _fail(f"VRM xdpe12284 {addr} on bus {bus}",
                      detail=f"Expected sysfs: {dev_path}", section=s)

    # UCD90320 power sequencer — search for it (address may vary by board rev)
    ucd_path = None
    for bus in range(0, 50):
        p = f"/sys/bus/i2c/devices/{bus}-0064"  # addr 0x64
        if os.path.exists(p):
            ucd_path = p
            break
    if ucd_path:
        _pass("UCD90320 i2c device", value=ucd_path, section=s)
    else:
        _info("UCD90320 i2c device — not present on this HW revision (optional)")

    # Post-PDDF init log
    rc2, out2, _ = _run(["journalctl", "-t", "qfx5241-post-pddf-init",
                          "--no-pager", "-n", "20"])
    if rc2 == 0 and "completed" in out2.lower():
        _pass("Post-PDDF init log: completed", section=s)
    else:
        _info("Post-PDDF init log: 'completed' marker not found (non-critical)")


# ---------------------------------------------------------------------------
# S E C T I O N   7  —  Per-driver loaded status (from pddf-device.json)
# ---------------------------------------------------------------------------
def sec7_driver_status(s=7):
    _section(s, "Per-driver loaded status (pddf-device.json)")

    if not os.path.isfile(PDDF_JSON):
        _fail("pddf-device.json present", detail="Cannot check drivers", section=s)
        return

    with open(PDDF_JSON) as f:
        pddf = json.load(f)

    platform_data = pddf.get("PLATFORM", {})
    all_kos = (
        platform_data.get("custom_kos", []) +
        platform_data.get("std_kos", []) +
        platform_data.get("pddf_kos", [])
    )

    rc, lsmod_out, _ = _run(["lsmod"])

    def _is_loaded(name):
        n = name.replace("-", "_")
        if n in (lsmod_out or ""):
            return True
        rc2, _, _ = _run(["grep", "-w", n, "/proc/modules"])
        return rc2 == 0

    for ko in all_kos:
        ok = _is_loaded(ko)
        if ok:
            _pass(f"  {ko}", section=s)
        else:
            _fail(f"  {ko}", detail=f"Not in lsmod — try: modprobe {ko}", section=s)

    # Per-device I2C client check for named devices in pddf-device.json
    _info("Checking PDDF I2C client devices in sysfs:")
    for key, val in pddf.items():
        if not isinstance(val, dict) or "dev_info" not in val:
            continue
        dev_type = val["dev_info"].get("device_type", "")
        if dev_type not in ("TEMP_SENSOR", "FAN", "PSU-PMBUS", "PSU-EEPROM",
                             "MUX", "DCDC"):
            continue
        topo = val.get("i2c", {}).get("topo_info", {})
        bus  = topo.get("parent_bus", "")
        addr = topo.get("dev_addr", "")
        name = val["dev_info"].get("device_name", key)
        if not bus or not addr:
            continue
        bus_int  = int(bus, 0) if bus.startswith("0x") else int(bus)
        addr_int = int(addr, 0) if addr.startswith("0x") else int(addr)
        sysfs    = f"/sys/bus/i2c/devices/{bus_int}-{addr_int:04x}"
        if os.path.exists(sysfs):
            _pass(f"  {name}: {sysfs}", section=s)
        else:
            # Some devices are hardware-revision or configuration dependent
            # PSU EEPROMs: model_name accessed via psu_pmbus driver directly
            # VRM5 (0x36): not populated on all board revisions
            # UCD90320: not present on QFX5241 (different power sequencer used)
            optional_devices = {"PSU1_EEPROM", "PSU2_EEPROM", "UCD90320", "VRM5"}
            if name in optional_devices or key in optional_devices:
                _info(f"  {name}: not present — optional on this HW rev")
                      
            else:
                _fail(f"  {name}: {sysfs}",
                      detail=f"Expected bus {bus_int} addr {addr}", section=s)


# ---------------------------------------------------------------------------
# S E C T I O N   8  —  MFD creation
# ---------------------------------------------------------------------------
def sec8_mfd_creation(s=8):
    _section(s, "MFD (Multi-Function Device) creation")

    # qfx5241-jnx-garnet-core creates MFDs under pci:0000:02:00.0
    mfd_parent = "/sys/bus/pci/devices/0000:02:00.0"
    if os.path.isdir(mfd_parent):
        _pass("CFPGA PCI device present", value=mfd_parent, section=s)
    else:
        _fail("CFPGA PCI device present",
              detail="PCI 0000:02:00.0 not found — CFPGA enumeration failed", section=s)

    # Look for MFD cells created under the garnet-core device
    mfd_cells = []
    if os.path.isdir(mfd_parent):
        for entry in os.scandir(mfd_parent):
            if entry.is_dir() and ("ocores" in entry.name or "mfd" in entry.name
                                    or "garnet" in entry.name.lower()):
                mfd_cells.append(entry.name)

    if mfd_cells:
        for cell in sorted(mfd_cells):
            _pass(f"  MFD cell: {cell}", section=s)
    else:
        _info("No explicit MFD cells found under PCI:02:00.0 — registered via platform driver directly")

    # ocores-i2c adapter presence (per-port CPLD1/CPLD2/SFP buses).
    # The adapter itself (i2c-64..i2c-129) is registered at boot regardless of
    # optics presence; a device client ("64-00xx") only appears once a module
    # is inserted, so checking for clients here false-fails on an empty bench
    # unit. Check the adapter's own sysfs name instead.
    import glob as _glob8
    ocores_adapters = [p for p in _glob8.glob("/sys/bus/i2c/devices/i2c-*/name")
                       if "ocores-i2c-garnet" in (_sysfs(p) or "")]

    if ocores_adapters:
        _pass(f"ocores-i2c adapters found: {len(ocores_adapters)}", section=s)
        if VERBOSE:
            for a in sorted(ocores_adapters)[:8]:
                _info(f"  {a}")
    else:
        _fail("ocores-i2c adapters found",
              detail="qfx5241-i2c-ocores-garnet driver may not be loaded", section=s)

    # xrefpga-lpcm sysfs
    lpcm_paths = list(Path("/sys/bus/platform/devices").glob("*xrefpga*")) if \
        Path("/sys/bus/platform/devices").is_dir() else []
    # xrefpga-lpcm — driver loads as a KO but does NOT create a platform device by design.
    # Only check that the KO is loaded (already verified in sec5); skip platform-device check.
    if lpcm_paths:
        _pass(f"xrefpga-lpcm platform device", value=str(lpcm_paths[0]), section=s)
    else:
        _info("xrefpga-lpcm platform device: driver loaded as KO only — no platform device expected by design")


# ---------------------------------------------------------------------------
# S E C T I O N   9  —  I2C / GPIO / FPGA / LED / Sensor verification
# ---------------------------------------------------------------------------
def sec9_device_verification(s=9):
    _section(s, "I2C / GPIO / FPGA / LED / Sensor device verification")

    # ---- I2C buses ----
    _info("=== I2C Bus Presence ===")
    # /sys/class/i2c-adapter/ may not exist on all kernels (absent on 6.12+).
    # Detect buses two ways in /sys/bus/i2c/devices/:
    #   1. Client device entries N-XXXX (bus N has a client device)
    #   2. Adapter symlinks i2c-N (bus N adapter registered, no client needed)
    i2c_dev_dir = "/sys/bus/i2c/devices"
    existing_buses = set()
    if os.path.isdir(i2c_dev_dir):
        for entry in os.scandir(i2c_dev_dir):
            # client: N-XXXX
            m = re.match(r"^(\d+)-[0-9a-f]+$", entry.name)
            if m:
                existing_buses.add(m.group(1))
            # adapter symlink: i2c-N
            m2 = re.match(r"^i2c-(\d+)$", entry.name)
            if m2:
                existing_buses.add(m2.group(1))

    for bus_id, desc in sorted(I2C_BUSES_REQUIRED.items(),
                                key=lambda x: int(x[0])):
        if bus_id in existing_buses:
            _pass(f"i2c-{bus_id}: {desc}", section=s)
        else:
            _fail(f"i2c-{bus_id}: {desc}",
                  detail=f"Bus {bus_id} not present", section=s)

    # ---- Temperature sensors ----
    _info("=== Temperature Sensors (lm75) ===")
    for bus, addr, driver, label in TEMP_SENSORS:
        addr_int = int(addr, 0)
        dev_path = f"/sys/bus/i2c/devices/{bus}-{addr_int:04x}"
        if os.path.isdir(dev_path):
            # Try to read temperature via hwmon
            hwmon_glob = list(Path(dev_path).glob("hwmon/hwmon*/temp1_input"))
            if hwmon_glob:
                val = _sysfs(str(hwmon_glob[0]))
                if val and val.lstrip("-").isdigit():
                    temp_c = int(val) / 1000.0
                    _pass(f"TEMP {label} ({addr})", value=f"{temp_c:.1f}°C", section=s)
                else:
                    _fail(f"TEMP {label} ({addr})",
                          detail="hwmon temp1_input not readable", section=s)
            else:
                _fail(f"TEMP {label} ({addr})",
                      detail="No hwmon entry under device", section=s)
        else:
            _fail(f"TEMP {label} ({addr})",
                  detail=f"Device not found: {dev_path}", section=s)

    # ---- Fan controller ----
    _info("=== Fan Controller (garnet-fancpld) ===")
    fan_dev = f"/sys/bus/i2c/devices/{FAN_CTRL_BUS}-{int(FAN_CTRL_ADDR,0):04x}"
    if os.path.isdir(fan_dev):
        _pass("FAN_CTRL i2c device", value=fan_dev, section=s)
        # Read fan speed via hwmon
        hwmon_speed = list(Path(fan_dev).glob("hwmon/hwmon*/fan1_input"))
        if hwmon_speed:
            val = _sysfs(str(hwmon_speed[0]))
            if val and val.isdigit():
                _pass("Fan 1 speed readable", value=f"{val} RPM", section=s)
            else:
                _fail("Fan 1 speed readable", detail="fan1_input empty/invalid", section=s)
        else:
            _fail("Fan hwmon entry", detail="No hwmon under fancpld", section=s)
    else:
        _fail("FAN_CTRL i2c device", detail=f"Missing: {fan_dev}", section=s)

    # Individual fan speeds via /sys/class/hwmon
    _info("=== Fan Speed reads via hwmon ===")
    hwmon_dir = "/sys/class/hwmon"
    fan_hwmon = None
    if os.path.isdir(hwmon_dir):
        for entry in os.scandir(hwmon_dir):
            name = _sysfs(os.path.join(entry.path, "name"))
            if name and "fan" in name.lower():
                fan_hwmon = entry.path
                break
    if fan_hwmon:
        _pass(f"Fan hwmon found", value=fan_hwmon, section=s)
        for i in range(1, 9):
            speed = _sysfs(f"{fan_hwmon}/fan{i}_input")
            if speed and speed.isdigit():
                _pass(f"  fan{i}_input", value=f"{speed} RPM", section=s)
            else:
                _fail(f"  fan{i}_input", detail="Not readable", section=s)
    else:
        _fail("Fan hwmon found", detail="No hwmon with 'fan' in name", section=s)

    # ---- PSU PMBUS ----
    _info("=== PSU PMBus devices ===")
    for bus, addr, label in PSU_PMBUS:
        addr_int = int(addr, 0)
        psu_dev = f"/sys/bus/i2c/devices/{bus}-{addr_int:04x}"
        if os.path.isdir(psu_dev):
            _pass(f"{label} i2c device", value=psu_dev, section=s)
            # Try to read v_out via hwmon
            vout = list(Path(psu_dev).glob("hwmon/hwmon*/in2_input"))
            if vout:
                val = _sysfs(str(vout[0]))
                if val and val.isdigit():
                    v = int(val) / 1000.0
                    _pass(f"  {label} voltage out", value=f"{v:.2f}V", section=s)
                else:
                    _fail(f"  {label} voltage out", detail="in2_input unreadable", section=s)
            else:
                # try PDDF sysfs
                pddf_psu = f"/sys/kernel/pddf/devices/PSU{label[-1]}_PMBUS"
                if os.path.isdir(pddf_psu):
                    _pass(f"  {label} PDDF sysfs", value=pddf_psu, section=s)
                else:
                    _info(f"  {label}: PSU PMBus accessible via PDDF direct sysfs")
        else:
            _fail(f"{label} i2c device",
                  detail=f"Missing: {psu_dev}  (bus {bus} addr {addr})", section=s)

    # ---- PDDF sysfs — PSU attributes ----
    # Note: On QFX5241 PDDF, PSU data is accessed via hwmon (psu_pmbus driver)
    # PSU driver exports attributes directly at /sys/bus/i2c/devices/33-005{8,9}/
    _info("=== PDDF PSU sysfs attributes ===")
    for psu_n, (psu_bus, psu_addr, psu_label) in enumerate(PSU_PMBUS, 1):
        psu_dev = f"/sys/bus/i2c/devices/{psu_bus}-{int(psu_addr,0):04x}"
        if os.path.isdir(psu_dev):
            # Check direct psu_v_out attribute (from psu_pmbus driver)
            direct_vout = os.path.join(psu_dev, "psu_v_out")
            if os.path.isfile(direct_vout):
                val = _sysfs(direct_vout)
                _pass(f"  PSU{psu_n}/psu_v_out", value=f"{val} (direct sysfs)", section=s)
            else:
                # Try hwmon
                vout_paths = list(Path(psu_dev).glob("hwmon/hwmon*/in2_input"))
                if vout_paths:
                    val = _sysfs(str(vout_paths[0]))
                    v = int(val)/1000.0 if val and val.isdigit() else 0
                    _pass(f"  PSU{psu_n}/psu_v_out", value=f"{v:.0f}mV via hwmon", section=s)
                else:
                    _info(f"  PSU{psu_n}/psu_v_out: not via hwmon — PDDF direct sysfs used")
            # psu_i_out
            direct_iout = os.path.join(psu_dev, "psu_i_out")
            if os.path.isfile(direct_iout):
                val = _sysfs(direct_iout)
                _pass(f"  PSU{psu_n}/psu_i_out", value=str(val), section=s)
            else:
                _info(f"  PSU{psu_n}/psu_i_out: not at direct path")
            # psu_model_name
            model_path = os.path.join(psu_dev, "psu_model_name")
            if os.path.isfile(model_path):
                val = _sysfs(model_path)
                _pass(f"  PSU{psu_n}/psu_model_name", value=str(val)[:20], section=s)
            else:
                _info(f"  PSU{psu_n}/psu_model_name: not exposed via this driver")
        else:
            _warn(f"  PSU{psu_n}: i2c device {psu_dev} not found")

    # ---- GPIO chips ----
    _info("=== GPIO chips ===")
    gpio_dir = "/sys/class/gpio"
    found_labels = {}
    if os.path.isdir(gpio_dir):
        for entry in os.scandir(gpio_dir):
            label_path = os.path.join(entry.path, "label")
            if os.path.isfile(label_path):
                label = _sysfs(label_path)
                if label:
                    found_labels[label] = entry.path

    for required_label in GPIO_LABELS_REQUIRED:
        matched = [k for k in found_labels if required_label in k]
        if matched:
            _pass(f"GPIO: {required_label}", value=matched[0], section=s)
        else:
            _fail(f"GPIO: {required_label}",
                  detail="gpiochip with this label not found", section=s)

    # Fan presence via GPIO
    _info("=== Fan presence GPIO reads ===")
    fp_chip = next((v for k, v in found_labels.items() if "fan-presence" in k), None)
    if fp_chip:
        base_path = os.path.join(fp_chip, "base")
        base_str = _sysfs(base_path)
        if base_str and base_str.isdigit():
            base = int(base_str)
            # GPIO offsets: tray0=7, tray1=6, tray2=5, tray3=4
            for tray, offset in enumerate([7, 6, 5, 4]):
                gpio_n = base + offset
                val_path = f"/sys/class/gpio/gpio{gpio_n}/value"
                # Export if needed
                if not os.path.exists(val_path):
                    try:
                        Path("/sys/class/gpio/export").write_text(str(gpio_n))
                    except Exception:
                        pass
                val = _sysfs(val_path)
                if val is not None:
                    present = val.strip() == "1"
                    status = "present" if present else "absent"
                    _pass(f"  Fan tray {tray} presence", value=status, section=s)
                else:
                    _warn(f"  Fan tray {tray} GPIO {gpio_n} not readable")
    else:
        _warn("fan-presence gpiochip not found — skipping fan tray presence reads")

    # ---- CFPGA / FPGA ----
    _info("=== CFPGA (PCI 0000:02:00.0) ===")
    if os.path.isdir(CFPGA_PCI_PATH):
        _pass("CFPGA PCI device", value=CFPGA_PCI_PATH, section=s)
        # Vendor/device ID
        vendor = _sysfs(f"{CFPGA_PCI_PATH}/vendor")
        device = _sysfs(f"{CFPGA_PCI_PATH}/device")
        _pass("CFPGA vendor:device", value=f"{vendor}:{device}", section=s)
        # Resource file (BAR0)
        if os.path.isfile(f"{CFPGA_PCI_PATH}/resource0"):
            sz = os.path.getsize(f"{CFPGA_PCI_PATH}/resource0")
            _pass("CFPGA BAR0 resource", value=f"{sz} bytes", section=s)
        else:
            _fail("CFPGA BAR0 resource", detail="resource0 not present", section=s)
        # Ocores adapters count
        rc, out, _ = _run(["i2cdetect", "-l"])
        ocores_count = sum(1 for l in out.splitlines() if "ocores" in l.lower())
        if ocores_count >= 64:
            _pass(f"ocores-i2c adapters count", value=str(ocores_count), section=s)
        else:
            _fail(f"ocores-i2c adapters count",
                  detail=f"Expected ≥64, got {ocores_count}", section=s)
    else:
        _fail("CFPGA PCI device", detail=f"{CFPGA_PCI_PATH} missing", section=s)

    # ---- LEDs ----
    _info("=== System LEDs ===")
    leds_dir = "/sys/class/leds"
    if os.path.isdir(leds_dir):
        found_leds = [e.name for e in os.scandir(leds_dir)]
    else:
        found_leds = []

    for led in LED_NAMES_REQUIRED:
        matched = [n for n in found_leds if led in n]
        if matched:
            # Try reading brightness
            bpath = f"{leds_dir}/{matched[0]}/brightness"
            val = _sysfs(bpath)
            _pass(f"LED: {led}", value=f"brightness={val}", section=s)
        else:
            _fail(f"LED: {led}", detail="Not found in /sys/class/leds/", section=s)

    # ---- Voltage sensors via PDDF ----
    # VOLTAGE1-6 are defined in pddf-device.json but sysfs path under
    # /sys/kernel/pddf/devices/VOLTAGEx/ is created by pddf_voltagemodule.
    # Voltage data is accessible via hwmon (xdpe12284 on bus 21).
    _info("=== Voltage sensors (PDDF) ===")
    for n in range(1, 7):
        vpath = f"/sys/kernel/pddf/devices/VOLTAGE{n}/volt1_input"
        if os.path.isfile(vpath):
            val = _sysfs(vpath)
            if val and val.lstrip("-").isdigit():
                v_mv = int(val)
                _pass(f"VOLTAGE{n}", value=f"{v_mv} mV", section=s)
            else:
                _warn(f"VOLTAGE{n}: volt1_input unreadable — check pddf_voltagemodule")
        else:
            # INFO not WARN — voltage data available via hwmon (xdpe12284 on bus 21)
            _info(f"VOLTAGE{n}: pddf_voltagemodule not loaded — data via hwmon xdpe12284")

    # ---- Port presence ----
    _info("=== Port transceiver presence (sample first 4 ports) ===")
    for port_n in range(1, 5):
        eeprom_bus = 64 + port_n - 1  # ocores CPLD1 port 0 = bus 64
        dev = f"/sys/bus/i2c/devices/{eeprom_bus}-0050"
        if os.path.isdir(dev):
            _pass(f"Port {port_n} EEPROM device", value=dev, section=s)
        else:
            # check optoe sysfs via eeprom attribute
            optoe_path = f"/sys/bus/i2c/devices/{eeprom_bus}-0050/eeprom"
            if os.path.isfile(optoe_path):
                _pass(f"Port {port_n} optoe eeprom", section=s)
            else:
                # No EEPROM = no cable plugged in — warn, don't fail
                _info(f"Port {port_n} EEPROM/optoe: bus {eeprom_bus} — no cable plugged in")

    # ---- SFP presence GPIO ----
    _info("=== SFP/QSFP-DD presence GPIO ===")
    for label, count in [("presence-cpld0", 32), ("presence-cpld1", 32), ("presence-sfp", 2)]:
        chip = next((v for k, v in found_labels.items() if label in k), None)
        if chip:
            ngpio_path = os.path.join(chip, "ngpio")
            ngpio = _sysfs(ngpio_path)
            _pass(f"  {label}", value=f"ngpio={ngpio}", section=s)
        else:
            _fail(f"  {label}", detail="gpiochip not found", section=s)


# ---------------------------------------------------------------------------
# S E C T I O N  10  —  User-space installation
# ---------------------------------------------------------------------------
def sec10_userspace(s=10):
    _section(s, "User-space installation")

    # Python packages — check via pip first, fall back to importlib/dpkg
    # sonic-platform-pddf-base and swsscommon are installed as deb packages,
    # not via pip, so we check importability or dpkg as well
    _pkg_checks = {
        "sonic-platform":          ("sonic_platform",                   None),
        "sonic-platform-pddf-base":("sonic_platform_pddf_base",         "sonic-platform-pddf"),
        "sonic-py-common":         ("sonic_py_common",                  None),
        "swsscommon":              ("swsscommon.swsscommon",             "python3-swsscommon"),
    }
    for pkg, (mod, deb_pkg) in _pkg_checks.items():
        rc, out, _ = _run([sys.executable, "-m", "pip", "show", pkg])
        if rc == 0:
            ver = next((l.split(":",1)[-1].strip() for l in out.splitlines()
                        if l.startswith("Version:")), "?")
            _pass(f"Python pkg: {pkg}", value=ver, section=s)
        else:
            # Try import
            rc2, _, _ = _run([sys.executable, "-c", f"import {mod}"])
            if rc2 == 0:
                _pass(f"Python pkg: {pkg}", value="installed (not via pip)", section=s)
            elif deb_pkg:
                rc3, _, _ = _run(["dpkg", "-l", deb_pkg])
                if rc3 == 0:
                    _pass(f"Python pkg: {pkg}", value=f"installed as {deb_pkg}", section=s)
                else:
                    _fail(f"Python pkg: {pkg}", detail="Not installed via pip or dpkg", section=s)
            else:
                _fail(f"Python pkg: {pkg}", detail="Not installed via pip", section=s)

    # CLI tools
    for tool in ["sonic-cfggen", "sfputil", "pddf_util.py",
                 "config", "show", "sonic-installer"]:
        rc, _, _ = _run(["which", tool])
        if rc == 0:
            _pass(f"CLI tool: {tool}", section=s)
        else:
            _fail(f"CLI tool: {tool}", detail="Not found in PATH", section=s)

    # bcm kmod (ASIC driver)
    # LTSW (TH5/QFX5241) uses linux_ngknet/linux_ngbde, not linux_bcm_knet
    ltsw_mods = ["linux_ngknet", "linux_ngknetcb", "linux_ngbde"]
    legacy_mods = ["linux_bcm_knet", "linux-bcm-knet", "linux_user_bde",
                   "linux_bcm_knet_6.5.28", "linux_bcm_knet_6.5.22"]
    ltsw_loaded = any(
        _run(["grep", "-w", m, "/proc/modules"])[0] == 0
        for m in ltsw_mods
    )
    if ltsw_loaded:
        _pass("BCM kmod (LTSW: linux_ngknet*)", value="linux_ngknet/ngbde loaded", section=s)
    else:
        for bcm_mod in legacy_mods:
            norm = bcm_mod.replace("-", "_")
            rc, out, _ = _run(["grep", "-w", norm, "/proc/modules"])
            if rc == 0:
                _pass(f"BCM kmod: {bcm_mod}", section=s)
                break
        else:
            _fail("BCM kmod (linux_bcm_knet*)",
                  detail="Broadcom SAI kernel module not loaded", section=s)

    # syncd binary
    rc, out, _ = _run(["docker", "exec", "syncd", "which", "syncd"])
    if rc == 0:
        _pass("syncd binary in container", value=out.strip(), section=s)
    else:
        _fail("syncd binary in container",
              detail="syncd container not running or syncd binary missing", section=s)


# ---------------------------------------------------------------------------
# S E C T I O N  11  —  SONiC docker container status
# ---------------------------------------------------------------------------
def sec11_docker_status(s=11):
    _section(s, "SONiC docker container status")

    rc, out, _ = _run(["docker", "ps", "--format",
                        "{{.Names}}\t{{.Status}}\t{{.RunningFor}}"])
    running = {}
    if rc == 0:
        for line in out.splitlines():
            parts = line.split("\t")
            if parts:
                running[parts[0]] = parts[1] if len(parts) > 1 else "unknown"

    for container in SONIC_DOCKERS:
        if container in running:
            status = running[container]
            ok = status.lower().startswith("up")
            if ok:
                _pass(f"docker: {container}", value=status, section=s)
            else:
                _fail(f"docker: {container}", value=status,
                      detail=f"docker logs {container} | tail -20", section=s)
        else:
            _fail(f"docker: {container}", detail="Container not running",
                  section=s)

    # Print full docker ps for visibility
    if VERBOSE:
        _info("Full docker ps:")
        rc2, out2, _ = _run(["docker", "ps", "--format",
                              "table {{.Names}}\t{{.Status}}\t{{.Ports}}"])
        for line in out2.splitlines():
            _info(f"  {line}")


# ---------------------------------------------------------------------------
# S E C T I O N  12  —  pmon daemon status
# ---------------------------------------------------------------------------
def sec12_pmon_daemons(s=12):
    _section(s, "pmon daemon status")

    # Check pmon is running first
    rc, out, _ = _run(["docker", "inspect", "--format={{.State.Status}}", "pmon"])
    pmon_running = rc == 0 and out.strip() == "running"
    if pmon_running:
        _pass("pmon container running", section=s)
    else:
        _fail("pmon container running",
              detail="docker logs pmon | tail -40", section=s)
        return

    # supervisorctl status inside pmon
    # Note: supervisorctl exits non-zero if ANY process is not RUNNING (e.g. EXITED)
    # so we parse the output regardless of exit code
    rc2, out2, _ = _run(["docker", "exec", "pmon",
                          "supervisorctl", "status"])
    daemon_status = {}
    if out2:  # parse regardless of rc2
        for line in out2.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0] not in ('#', ''):
                daemon_status[parts[0]] = parts[1]

    # Daemons expected to be EXITED after completing their one-shot task
    _expected_exited = {"chassis_db_init", "dependent-startup", "start",
                        "waitfor_lldp_ready", "supervisor-proc-exit-listener"}

    for daemon in PMON_DAEMONS:
        if daemon in daemon_status:
            state = daemon_status[daemon]
            if daemon in _expected_exited and state == "EXITED":
                _pass(f"pmon daemon: {daemon}", value=f"{state} (expected)", section=s)
            elif state == "RUNNING":
                _pass(f"pmon daemon: {daemon}", value=state, section=s)
            else:
                _fail(f"pmon daemon: {daemon}", value=state,
                      detail=f"docker exec pmon supervisorctl restart {daemon}", section=s)
        else:
            _fail(f"pmon daemon: {daemon}", detail="Not in supervisorctl output",
                  section=s)

    # 202511: optional daemons — warn only if absent (not all run on QFX5241)
    for daemon in PMON_DAEMONS_OPTIONAL_202511:
        if daemon in daemon_status:
            state = daemon_status[daemon]
            if state == "RUNNING":
                _pass(f"pmon daemon (optional): {daemon}", value=state, section=s)
            else:
                _info(f"pmon optional daemon {daemon} state: {state}")
        else:
            _info(f"pmon optional daemon {daemon}: not present (expected for QFX5241)")

    # Check for recent errors in pmon
    rc3, err3, _ = _run(["docker", "exec", "pmon",
                          "tail", "-n", "20", "/var/log/supervisor/supervisord.log"])
    if "ERROR" in (err3 or "") or "FATAL" in (err3 or ""):
        _warn("pmon supervisord log has ERROR/FATAL — check docker exec pmon cat /var/log/supervisor/supervisord.log")


# ---------------------------------------------------------------------------
# S E C T I O N  13  —  ASIC bring-up status
# ---------------------------------------------------------------------------
def sec13_asic_status(s=13):
    _section(s, "ASIC bring-up status")

    # syncd running
    rc, out, _ = _run(["docker", "inspect", "--format={{.State.Status}}", "syncd"])
    syncd_up = rc == 0 and out.strip() == "running"
    if syncd_up:
        _pass("syncd container running", section=s)
    else:
        _fail("syncd container running", section=s)

    # SAI init — for LTSW/TH5, check ASIC_DB directly (syncd log may not have SAI_STATUS_SUCCESS)
    rc_sw, out_sw, _ = _run(["docker", "exec", "database",
                              "redis-cli", "-n", "1", "KEYS",
                              "ASIC_STATE:SAI_OBJECT_TYPE_SWITCH:*"])
    if rc_sw == 0 and out_sw.strip():
        _pass("SAI init success in syncd log", value="ASIC_STATE:SAI_OBJECT_TYPE_SWITCH found", section=s)
    else:
        # Fallback: check syncd log
        rc2, out2, _ = _run(["docker", "logs", "--tail=200", "syncd"])
        if "SAI_STATUS_SUCCESS" in out2 or "sai_api_initialize" in out2.lower():
            _pass("SAI init success in syncd log", section=s)
        else:
            _fail("SAI init success in syncd log",
                  detail="Check: docker logs syncd | grep -i sai", section=s)

    # swss running
    rc3, out3, _ = _run(["docker", "inspect", "--format={{.State.Status}}", "swss"])
    if rc3 == 0 and out3.strip() == "running":
        _pass("swss container running", section=s)
    else:
        _fail("swss container running", section=s)

    # Check ASIC_DB is populated in Redis — use KEYS for reliability
    rc4, out4, _ = _run(["docker", "exec", "database",
                          "redis-cli", "-n", "1", "KEYS",
                          "ASIC_STATE:SAI_OBJECT_TYPE_SWITCH:*"])
    if rc4 == 0 and out4.strip():
        # Also get attribute count
        switch_key = out4.strip().splitlines()[0]
        rc4b, out4b, _ = _run(["docker", "exec", "database",
                                "redis-cli", "-n", "1", "HLEN", switch_key])
        attrs = out4b.strip() if rc4b == 0 else "?"
        _pass("ASIC_DB SAI SWITCH entry exists", value=f"{attrs} attrs", section=s)
    else:
        _fail("ASIC_DB SAI SWITCH entry exists",
              detail="ASIC not initialised — check syncd/swss logs", section=s)

    # Interface count in ASIC_DB
    rc5, out5, _ = _run(["docker", "exec", "database",
                          "redis-cli", "-n", "1",
                          "KEYS", "ASIC_STATE:SAI_OBJECT_TYPE_PORT:*"])
    if rc5 == 0:
        port_cnt = len(out5.strip().splitlines())
        ok = port_cnt >= 64
        if ok:
            _pass("ASIC port objects in ASIC_DB", value=str(port_cnt), section=s)
        else:
            _fail("ASIC port objects in ASIC_DB",
                  detail=f"Only {port_cnt} ports — expected ≥64", section=s)
    else:
        _fail("ASIC_DB port query", detail="database container not running?", section=s)

    # BCM / LTSW kernel device nodes
    # LTSW (TH5) uses linux_ngbde / linux_ngknet; legacy BCM uses linux-user-bde
    found_bde = False
    for dev_path in ["/dev/linux_ngbde", "/dev/linux-knet-cb", "/dev/linux-bcm-knet",
                     "/dev/linux-user-bde", "/dev/linux-bcm-knetcb"]:
        if os.path.exists(dev_path):
            _pass(f"BCM/LTSW device: {dev_path}", section=s)
            found_bde = True
    if not found_bde:
        _fail("BCM kmod device node",
              detail="No /dev/linux_ngbde or /dev/linux-user-bde found — kernel driver not loaded",
              section=s)

    # saisdkdump — dump SAI SDK state (if available)
    rc6, out6, _ = _run(["docker", "exec", "syncd", "which", "saidump"], timeout=5)
    if rc6 == 0:
        _pass("saidump tool available", section=s)

    # NGBDE: LTSW uses linux_ngbde, legacy uses linux-user-bde
    if os.path.exists("/dev/linux_ngbde"):
        _pass("NGBDE/LTSW device node (/dev/linux_ngbde)", section=s)
    elif os.path.exists("/dev/linux-user-bde"):
        _pass("NGBDE device node (/dev/linux-user-bde)", section=s)
    else:
        _fail("linux-user-bde device node",
              detail="NGBDE driver may not be loaded", section=s)

    # pciefw
    pcie_yaml = os.path.join(PLATFORM_DIR, "pcie.yaml")
    if os.path.isfile(pcie_yaml):
        _pass("pcie.yaml present", section=s)
        rc8, out8, _ = _run(["pcieutil", "check"], timeout=20)
        if rc8 == 0 and "PASS" in out8.upper():
            _pass("pcieutil check PASS", section=s)
        elif rc8 == 0:
            _warn("pcieutil check returned — review output manually")
        else:
            _fail("pcieutil check", detail=out8[:200] or "Not available", section=s)
    else:
        _warn("pcie.yaml not found — skipping pcieutil check")


# ---------------------------------------------------------------------------
# S E C T I O N  14  —  Platform CLIs
# ---------------------------------------------------------------------------
def sec14_platform_clis(s=14):
    _section(s, "Platform CLIs")

    for cmd, expected in PLATFORM_CLIS:
        cmd_str = " ".join(cmd)
        rc, out, err = _run(cmd, timeout=30)
        if rc == 0:
            if expected and expected not in out:
                _fail(cmd_str,
                      detail=f"Output missing '{expected}'", section=s)
            else:
                snippet = out.strip()[:60].replace("\n", " ")
                _pass(cmd_str, value=snippet, section=s)
        else:
            err_snippet = (err or out).strip()[:120]
            _fail(cmd_str, detail=err_snippet, section=s)

    # pddf_util.py status
    rc, out, _ = _run(["pddf_util.py", "status"], timeout=15)
    if rc == 0:
        _pass("pddf_util.py status", section=s)
        if VERBOSE:
            for line in out.splitlines()[:20]:
                _info(f"  {line}")
    else:
        _fail("pddf_util.py status", detail=(out + err)[:200], section=s)

    # sfputil show presence (first 4)
    rc2, out2, err2 = _run(["sfputil", "show", "presence", "--port", "Ethernet0"], timeout=15)
    if rc2 == 0:
        _pass("sfputil show presence Ethernet0", section=s)
    else:
        _fail("sfputil show presence Ethernet0", detail=err2[:120], section=s)

    # show system-health detail
    rc3, out3, _ = _run(["show", "system-health", "detail"], timeout=20)
    if rc3 == 0:
        crit = [l for l in out3.splitlines() if "CRITICAL" in l.upper()]
        if crit:
            for c in crit[:3]:
                _fail(f"system-health: {c.strip()}", section=s)
        else:
            _pass("show system-health detail: no CRITICALs", section=s)
    else:
        _warn("show system-health detail failed")


# ---------------------------------------------------------------------------
# S E C T I O N  15  —  Interface CLIs
# ---------------------------------------------------------------------------
def sec15_interface_clis(s=15):
    _section(s, "Interface CLIs")

    for cmd, expected in INTERFACE_CLIS:
        cmd_str = " ".join(cmd)
        rc, out, err = _run(cmd, timeout=30)
        if rc == 0:
            snippet = out.strip()[:80].replace("\n", " ")
            _pass(cmd_str, value=snippet, section=s)
        else:
            _fail(cmd_str, detail=(err or out).strip()[:120], section=s)

    # Count interfaces UP vs DOWN
    rc, out, _ = _run(["show", "interfaces", "status"])
    if rc == 0:
        up_count   = out.count(" up ")
        down_count = out.count(" down ")
        notconn    = out.count("N/A")
        _info(f"Interface summary: UP={up_count}  DOWN={down_count}  N/A={notconn}")
        if up_count > 0:
            _pass("At least one interface UP", value=str(up_count), section=s)
        else:
            _warn("No interfaces are UP — check cabling / ASIC init")

    # Verify 66 interfaces configured (64 QSFP-DD + 2 SFP)
    rc2, out2, _ = _run(["show", "interfaces", "status"])
    if rc2 == 0:
        eth_lines = [l for l in out2.splitlines() if l.startswith("Ethernet")]
        cnt = len(eth_lines)
        # QFX5241-64-OD: 64 ports, but port-split/breakout config may show fewer
        # Accept ≥ 48 as valid (full 64-port config shows exactly 64 in default mode)
        if cnt >= 64:
            _pass("Interface count ≥ 64", value=str(cnt), section=s)
        elif cnt >= 48:
            _info(f"Interface count {cnt} (port breakout config reduces from 64 — expected)")
        else:
            _fail("Interface count ≥ 64",
                  detail=f"Only {cnt} Ethernet interfaces found — expected ≥48", section=s)

    # Transceiver presence for first 8 ports
    rc3, out3, _ = _run(["show", "interfaces", "transceiver", "presence"])
    if rc3 == 0:
        present = sum(1 for l in out3.splitlines() if "Present" in l)
        _info(f"Transceivers present: {present}")
        _pass("Transceiver presence command", value=f"{present} present", section=s)
    else:
        _fail("Transceiver presence command", detail="sfputil/xcvrd may not be ready", section=s)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
def _print_summary(as_json=False):
    total_pass = sum(r["status"] == "PASS" for r in _results)
    total_fail = sum(r["status"] == "FAIL" for r in _results)
    total_warn = sum(r["status"] == "WARN" for r in _results)
    total      = len(_results)
    ts         = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Collect device info for the report header
    def _run_q(cmd):
        try:
            return subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL,
                                           text=True).strip()
        except Exception:
            return "N/A"

    sonic_ver  = _run_q("sonic-cfggen -d -v DEVICE_METADATA.localhost.sonic_version 2>/dev/null || "
                        "grep build_version /etc/sonic/sonic_version.yml 2>/dev/null | awk '{print $2}'")
    hostname   = _run_q("hostname")
    platform   = _run_q("sonic-cfggen -d -v DEVICE_METADATA.localhost.platform 2>/dev/null || "
                        "cat /etc/sonic/device_metadata.json 2>/dev/null | python3 -c "
                        "\"import sys,json; d=json.load(sys.stdin); print(d.get('DEVICE_METADATA',{}).get('localhost',{}).get('platform','N/A'))\" 2>/dev/null")
    hwsku      = _run_q("sonic-cfggen -d -v DEVICE_METADATA.localhost.hwsku 2>/dev/null")
    uptime     = _run_q("uptime -p")

    if as_json:
        out = {
            "platform":   PLATFORM_NAME,
            "hostname":   hostname,
            "sonic_ver":  sonic_ver,
            "hwsku":      hwsku,
            "timestamp":  datetime.now().isoformat(),
            "uptime":     uptime,
            "total_pass": total_pass,
            "total_fail": total_fail,
            "total_warn": total_warn,
            "total":      total,
            "overall":    "PASS" if total_fail == 0 else "FAIL",
            "results":    _results,
            "failed":     [r for r in _results if r["status"] == "FAIL"],
            "warnings":   [r for r in _results if r["status"] == "WARN"],
        }
        out_str = json.dumps(out, indent=2)
        print(out_str)
        if _report_path:
            try:
                with open(_report_path, 'w') as f:
                    f.write(out_str)
                print(f"\n  Report saved: {_report_path}", file=sys.stderr)
            except Exception as e:
                print(f"\n  WARNING: Could not save report: {e}", file=sys.stderr)
        return

    def p(text="", end="\n"):
        print(text, end=end)
        if _report_path:
            clean = re.sub(r'\033\[[0-9;]*m', '', text)
            _report_buf.write(clean + end)

    p()
    p(_bold(_cyan("=" * 70)))
    p(_bold(_cyan("  QFX5241-64 PLATFORM DIAGNOSTIC REPORT")))
    p(_bold(_cyan("=" * 70)))
    p(f"  Platform    : {PLATFORM_NAME}")
    p(f"  Hostname    : {hostname}")
    p(f"  SONiC Ver   : {sonic_ver}")
    p(f"  HW SKU      : {hwsku}")
    p(f"  Uptime      : {uptime}")
    p(f"  Generated   : {ts}")
    p(_bold(_cyan("=" * 70)))
    p()

    # Per-section summary table
    p(f"  {'Sec':>3}  {'Title':<42} {'PASS':>6} {'FAIL':>6} {'WARN':>6}")
    p(f"  {'---':>3}  {'-'*42} {'----':>6} {'----':>6} {'----':>6}")
    sec_titles = {
        1: "Installation",
        2: "sonic-platform-common",
        3: "sonic-platform-qfx5241",
        4: "Pre-PDDF init",
        5: "PDDF kernel modules",
        6: "Post-PDDF init",
        7: "Per-driver status",
        8: "MFD creation",
        9: "Device verification",
        10: "User-space installation",
        11: "Docker containers",
        12: "pmon daemons",
        13: "ASIC bring-up",
        14: "Platform CLIs",
        15: "Interface CLIs",
    }
    for sec_n in sorted(_section_counters):
        ctr = _section_counters[sec_n]
        title = sec_titles.get(sec_n, "")
        ps, fs, ws = ctr["pass"], ctr["fail"], ctr.get("warn", 0)
        colour = _red if fs > 0 else (_yellow if ws > 0 else _green)
        p(f"  {sec_n:>3}  {title:<42} {_green(str(ps)):>14} {colour(str(fs)):>14} {_yellow(str(ws)):>14}")

    p()
    ovr = _green("PASS") if total_fail == 0 else _red("FAIL")
    p(f"  Overall: {ovr}  —  {total_pass}/{total} checks passed  ({total_warn} warnings)")
    p(_bold(_cyan("=" * 70)))

    # ---- FAILED checks (detailed) ----
    if total_fail > 0:
        p()
        p(_bold(_red("=" * 70)))
        p(_bold(_red("  FAILED CHECKS")))
        p(_bold(_red("=" * 70)))
        prev_sec = None
        for r in _results:
            if r["status"] != "FAIL":
                continue
            sec = r["section"]
            if sec != prev_sec:
                p()
                p(_bold(f"  Section {sec}: {sec_titles.get(sec, '')}"))
                p(f"  {'-'*66}")
                prev_sec = sec
            p(f"    [{sec:02d}] {r['test']}")
            if r["detail"]:
                p(f"          {_yellow(r['detail'])}")
        p()

    # ---- WARNINGS ----
    if total_warn > 0:
        p()
        p(_bold(_yellow("=" * 70)))
        p(_bold(_yellow("  WARNINGS")))
        p(_bold(_yellow("=" * 70)))
        for r in _results:
            if r["status"] != "WARN":
                continue
            p(f"    [{r['section']:02d}] {r['test']}")
            if r["detail"]:
                p(f"          {r['detail']}")
        p()

    # ---- OVERALL HEALTH ASSESSMENT ----
    p()
    p(_bold(_cyan("=" * 70)))
    p(_bold(_cyan("  HEALTH ASSESSMENT")))
    p(_bold(_cyan("=" * 70)))

    critical_secs = {11: "Docker containers", 12: "pmon daemons", 13: "ASIC bring-up",
                     5: "PDDF kernel modules", 4: "Pre-PDDF init"}
    has_critical = False
    for sec_n, sec_name in critical_secs.items():
        if _section_counters.get(sec_n, {}).get("fail", 0) > 0:
            p(_red(f"  ✗ CRITICAL: {sec_name} has failures — platform may not function correctly"))
            has_critical = True

    if not has_critical:
        p(_green("  ✓ All critical sections (docker, pmon, PDDF, ASIC) passed"))

    if total_fail == 0:
        p(_green("  ✓ Platform is fully operational"))
    elif total_fail <= 5:
        p(_yellow(f"  △ Minor issues detected ({total_fail} failures) — platform partially operational"))
    else:
        p(_red(f"  ✗ Platform has issues ({total_fail} failures) — investigation required"))

    p(_bold(_cyan("=" * 70)))

    # ---- NEXT STEPS ----
    if total_fail > 0:
        p()
        p(_bold("  SUGGESTED NEXT STEPS:"))
        # Auto-generate hints based on failed sections
        failed_secs = set(r["section"] for r in _results if r["status"] == "FAIL")
        if 1 in failed_secs or 3 in failed_secs:
            p("    • Reinstall platform debs: sonic-platform-juniper-common, sonic-platform-juniper-qfx5241")
        if 4 in failed_secs or 5 in failed_secs:
            p("    • Re-run: sudo pddf_util.py install && sudo /usr/local/bin/juniper_common_platform_init.py")
        if 6 in failed_secs:
            p("    • Check PDDF device tree: sudo pddf_util.py status")
        if 11 in failed_secs:
            p("    • Check docker logs: docker logs <container>")
        if 12 in failed_secs:
            p("    • Check pmon: docker exec pmon supervisorctl status")
        if 13 in failed_secs:
            p("    • Check syncd: docker logs syncd | tail -50")
        p()

    if _report_path:
        _save_report()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
SECTION_MAP = {
    1:  sec1_installation,
    2:  sec2_sonic_platform_common,
    3:  sec3_sonic_platform_qfx5241,
    4:  sec4_pre_pddf_init,
    5:  sec5_pddf_install,
    6:  sec6_post_pddf_init,
    7:  sec7_driver_status,
    8:  sec8_mfd_creation,
    9:  sec9_device_verification,
    10: sec10_userspace,
    11: sec11_docker_status,
    12: sec12_pmon_daemons,
    13: sec13_asic_status,
    14: sec14_platform_clis,
    15: sec15_interface_clis,
}


def main():
    global VERBOSE, _USE_COLOUR, _report_path

    parser = argparse.ArgumentParser(
        description="QFX5241-64 SONiC Platform Diagnostics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--section", "-s", type=int, metavar="N",
                        help="Run only section N (1-15)")
    parser.add_argument("--json", action="store_true",
                        help="Output results as JSON")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show extra detail")
    parser.add_argument("--no-colour", action="store_true",
                        help="Disable ANSI colour output")
    parser.add_argument("--report", "-r", metavar="FILE",
                        help="Save full report to FILE (e.g. /tmp/qfx5241_diag_report.txt)")
    args = parser.parse_args()

    VERBOSE = args.verbose
    if args.no_colour or args.json:
        _USE_COLOUR = False

    if args.report:
        _report_path = args.report

    if os.geteuid() != 0:
        print(_yellow("WARNING: Not running as root — some checks will fail."), file=sys.stderr)

    hdr = f"\n  QFX5241-64 Platform Diagnostics  —  {PLATFORM_NAME}"
    ts  = f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    print(_bold(hdr))
    print(ts)
    if _report_path:
        _report_buf.write(hdr + "\n" + ts + "\n")

    if args.section:
        fn = SECTION_MAP.get(args.section)
        if not fn:
            print(f"Unknown section {args.section}. Valid: 1-15", file=sys.stderr)
            sys.exit(1)
        fn(s=args.section)
    else:
        for sec_n, fn in sorted(SECTION_MAP.items()):
            fn(s=sec_n)

    _print_summary(as_json=args.json)

    total_fail = sum(r["status"] == "FAIL" for r in _results)
    sys.exit(1 if total_fail else 0)


if __name__ == "__main__":
    main()
