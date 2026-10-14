#!/usr/bin/env python3
#
# utils.py — Shared utility functions for Juniper SONiC platform code.
#
# Centralised here so that platform/juniper/ can be removed without
# duplicating helpers in every per-platform init script or sonic_platform
# class.  All public symbols here are safe to import from any context.

import os
import re
import glob
import subprocess
from pathlib import Path
from sonic_py_common.logger import Logger

SYSLOG_IDENTIFIER = "platform-init"

# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------

def log_info(msg, ident=None):
    Logger(ident or SYSLOG_IDENTIFIER).log_info(msg)


def log_error(msg, ident=None):
    Logger(ident or SYSLOG_IDENTIFIER).log_error(msg)


def log_warning(msg, ident=None):
    Logger(ident or SYSLOG_IDENTIFIER).log_warning(msg)


def log_debug(msg, ident=None):
    Logger(ident or SYSLOG_IDENTIFIER).log_debug(msg)


def log_critical(msg, ident=None):
    Logger(ident or SYSLOG_IDENTIFIER).log_critical(msg)


def log_notice(msg, ident=None):
    Logger(ident or SYSLOG_IDENTIFIER).log_notice(msg)


# ---------------------------------------------------------------------------
# Shell execution helpers
# ---------------------------------------------------------------------------

def run_cmd(cmd):
    """Run a shell command; returns stdout bytes (may be None)."""
    res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE)
    return res.stdout


def log_os_system(cmd, show=1):
    """Run a shell command, capture stdout+stderr, and return (rc, output).

    If the command fails and *show* is truthy the error is logged via syslog.
    """
    process = subprocess.Popen(
        cmd, shell=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    output, _ = process.communicate()
    status = process.returncode
    if status and show:
        log_error(f"Failed: {cmd}", SYSLOG_IDENTIFIER)
    return status, output


# ---------------------------------------------------------------------------
# hwmon helpers
# ---------------------------------------------------------------------------

def get_hwmon_path(hwmon_name=None, index=0):
    hwmon_paths = []
    HWMON_PATH = "/sys/class/hwmon"
    name_file = []
    for entry in sorted(os.listdir(HWMON_PATH)):
        dir_path = os.path.join(HWMON_PATH, entry)
        if os.path.isdir(dir_path):
            name_file.append(os.path.join(dir_path, "name"))
            name_file.append(os.path.join(dir_path, "device", "name"))
        for namefile in name_file:
            if os.path.isfile(namefile):
                with open(namefile, "r") as f:
                    name = f.read().strip()
                    if name == hwmon_name:
                        hwmon_paths.append(dir_path)
                        break
    return hwmon_paths[index]


def get_hwmon_path_from_addr(mux_path=None, channel_name=None, bus=None, addr=None):
    I2C_DEVICE_PATH = '/sys/bus/i2c/devices'
    if bus:
        hwmon_path = f"{I2C_DEVICE_PATH}/i2c-{bus}/{bus}-{addr:04x}/hwmon/hwmon*"
    if mux_path:
        hwmon_path = f"{mux_path}/{channel_name}/*-{addr:04x}/hwmon/hwmon*"
    paths = glob.glob(hwmon_path)
    if paths:
        return paths[0]
    return None


def get_hwmon_value(hwmon_path, hwmon_param):
    file_path = os.path.join(hwmon_path, hwmon_param)
    if not os.path.isfile(file_path):
        log_error(f"File not found: {file_path}", SYSLOG_IDENTIFIER)
        return None
    try:
        with open(file_path, "r") as f:
            value_str = f.read().strip()
            if "led" in hwmon_param:
                return value_str
            elif "temp" in hwmon_param:
                return float(value_str)
            else:
                return int(value_str)
    except Exception as e:
        log_error(f"Error reading {file_path}: {e}", SYSLOG_IDENTIFIER)
        return None


def set_hwmon_value(hwmon_path, parameter, value):
    file_path = os.path.join(hwmon_path, parameter)
    if not os.path.isfile(file_path):
        return False
    try:
        with open(file_path, "w") as f:
            f.write(str(value))
        return True
    except PermissionError:
        log_error(f"Permission denied: {file_path}", SYSLOG_IDENTIFIER)
        return False
    except Exception as e:
        log_error(f"Error writing to {file_path}: {e}", SYSLOG_IDENTIFIER)
        return False


# ---------------------------------------------------------------------------
# GPIO helpers
# ---------------------------------------------------------------------------

def get_gpiochip_base_from_label(gpio_label):
    GPIOCHIP_LABEL_PATH = "/sys/class/gpio/gpiochip*/label"
    base = int()
    paths = glob.glob(GPIOCHIP_LABEL_PATH)
    for p in paths:
        try:
            with open(p, 'r') as f:
                label = f.read().strip()
            if label == gpio_label:
                res = re.search(r"gpiochip(\d+)", p)
                if res:
                    return int(res.group(1))
        except Exception:
            return None
    return base


def get_gpiopin_value(pin):
    data = str()
    try:
        with open(f"/sys/class/gpio/gpio{pin}/value", "r") as fd:
            data = fd.read()
    except Exception:
        pass
    return int(data.strip())


def gpio_control(pin, direction, value=None):
    """Control GPIO pin direction and optionally read/write its value.

    direction: "high" | "low" | "out" | "in"
    Returns (status: bool, val: int|None).
    """
    if direction in ["high", "low"]:
        status = set_gpiopin_direction(pin, direction)
        return status, None
    elif direction == "out":
        status = set_gpiopin_direction(pin, "out")
        if not status:
            return False, None
        status = set_gpiopin_value(pin, value)
        return status, None
    elif direction == "in":
        status = set_gpiopin_direction(pin, "in")
        if not status:
            return False, None
        val = get_gpiopin_value(pin)
        return True, val
    else:
        log_error(f"Invalid direction: {direction}", SYSLOG_IDENTIFIER)
        return False, None


def gpio_export(pin):
    """Export GPIO pin to sysfs if not already exported."""
    pin_path = f"/sys/class/gpio/gpio{pin}"
    if not os.path.exists(pin_path):
        try:
            with open("/sys/class/gpio/export", "w") as fd:
                fd.write(str(pin))
        except OSError:
            pass  # already exported or unavailable


def set_gpiopin_direction(pin, direction):
    valid_dirs = ["in", "out", "high", "low"]
    if direction not in valid_dirs:
        log_error(f"Invalid direction: {direction}", SYSLOG_IDENTIFIER)
        return False
    gpio_export(pin)
    try:
        with open(f"/sys/class/gpio/gpio{pin}/direction", "w") as fd:
            fd.write(direction)
    except Exception as e:
        log_error(f"Error: {e}", SYSLOG_IDENTIFIER)
        return False
    return True


def set_gpiopin_value(pin, value):
    gpio_export(pin)
    try:
        with open(f"/sys/class/gpio/gpio{pin}/value", "w") as fd:
            fd.write(str(value))
    except Exception as e:
        log_error(f"Error: {e}", SYSLOG_IDENTIFIER)
        return False
    return True


# ---------------------------------------------------------------------------
# I2C / bus helpers
# ---------------------------------------------------------------------------

def detect_i2c_bus(mux_path=None, channel=None):
    if not mux_path or not os.path.isdir(mux_path):
        log_error(f"Path does not exist: {mux_path}", SYSLOG_IDENTIFIER)
        return None
    if channel:
        full_path = os.path.join(mux_path, channel)
    else:
        full_path = mux_path
    full_path = full_path.rstrip('/')
    if os.path.islink(full_path):
        target = os.readlink(full_path).split('/')[-1]
        match = re.search(r"i2c-(\d+)", target)
        if match:
            return int(match.group(1))
    return None


def read_i2c_register(bus, address, register='0x33', mode='b', length=0):
    try:
        address_str = hex(address) if isinstance(address, int) else address
        register_str = hex(register) if isinstance(register, int) else register
        if length > 0:
            cmd = ["i2cget", "-f", "-y", str(bus), address_str, register_str, "i", str(length)]
        else:
            cmd = ["i2cget", "-f", "-y", str(bus), address_str, register_str]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0 or not result.stdout:
            return None
        hex_values = [int(x, 16) for x in re.findall(r'0x[0-9a-fA-F]+', result.stdout)]
        if not hex_values:
            return None
        if length > 0 and len(hex_values) > 1:
            return hex_values[1:]
        return hex_values
    except Exception as e:
        log_error(f"Error: {e}", SYSLOG_IDENTIFIER)
        return None


def get_bus_from_device_string(pci_device: str, match_str: str) -> int:
    """Scan /sys/bus/pci/devices/<pci_device>/<match_str>/ for i2c-<n> entries."""
    dev = -1
    pname = f"/sys/bus/pci/devices/{pci_device}/{match_str}/"
    try:
        entries = os.listdir(pname)
    except FileNotFoundError:
        return dev
    for entry in entries:
        m = re.match(r"^i2c-(\d+)$", entry)
        if m:
            dev = int(m.group(1))
            break
    return dev


def get_i2c_bus_numbers_for_muxes(pci_dev_path=None, mux_name_pattern=None):
    """Return sorted child I2C bus numbers under PCI mux driver directories."""
    bus_numbers = []
    if not pci_dev_path or not mux_name_pattern:
        return []
    mux_dirs = glob.glob(os.path.join(pci_dev_path, mux_name_pattern))
    if not mux_dirs:
        log_error(
            f"No directories matching {mux_name_pattern} found under {pci_dev_path}",
            SYSLOG_IDENTIFIER,
        )
        return []
    pattern = os.path.join(pci_dev_path, mux_name_pattern, "i2c-*")
    for path in glob.glob(pattern):
        name = os.path.basename(path)
        match = re.match(r"i2c-(\d+)", name)
        if match:
            bus_numbers.append(int(match.group(1)) + 1)
    return sorted(bus_numbers)


# ---------------------------------------------------------------------------
# SKU symlink helper
# ---------------------------------------------------------------------------

def setup_sku_symlinks(platform=None, hwsku=None):
    """Create platform.json / default_sku / media_settings.json symlinks for a SKU."""
    if not platform or not hwsku:
        return None
    base_dir = Path("/usr/share/sonic/device")
    platform_dir = base_dir / platform
    sku_dir = platform_dir / hwsku
    if (not sku_dir.is_dir()
            or not (sku_dir / "platform.json").is_file()
            or not (sku_dir / "hwsku_name").is_file()
            or not (sku_dir / "media_settings.json").is_file()):
        return None
    target_json = platform_dir / "platform.json"
    target_default = platform_dir / "default_sku"
    target_media_settings = platform_dir / "media_settings.json"
    for t in (target_json, target_default, target_media_settings):
        if t.exists() or t.is_symlink():
            t.unlink(missing_ok=True)
    try:
        target_json.symlink_to(sku_dir / "platform.json")
        target_default.symlink_to(sku_dir / "hwsku_name")
        target_media_settings.symlink_to(sku_dir / "media_settings.json")
    except OSError as e:
        log_error(f"Error creating symlinks: {e}", SYSLOG_IDENTIFIER)
        return None
