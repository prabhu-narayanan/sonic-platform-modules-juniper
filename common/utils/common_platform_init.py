#!/usr/bin/env python3
#
# common_platform_init.py — Generic Juniper platform initialization.
#
# Runs from juniper-common-platform-init.service (owned by
# sonic-platform-juniper-common).  Contains ONLY tasks that are safe on
# every Juniper broadcom platform, regardless of whether it uses the
# i2c-static or PDDF driver model:
#
#   1. Point EFI BootNext at the SONiC-OS entry (boot-order fixup)
#   2. Resize /var/log partition to 32 G if needed
#   3. Copy ONIE EEPROM cache to /var/run/platform_cache/
#   4. Copy platform firmware binaries to /usr/bin/
#   5. Set eth0 base MAC address from syseeprom
#
# Platform-specific device setup (i2c mux registration, kernel module
# loading, PDDF bringup) is intentionally NOT done here.  Each
# platform-specific package (sonic-platform-juniper-qfx52xx etc.) owns
# its own service for that work.

from sonic_py_common import device_info
from sonic_py_common.general import getstatusoutput_noshell
from sonic_platform.utils import log_os_system

import glob
import os
import re
import time
import subprocess
import shutil


SONIC_BOOT_LABEL = 'SONiC-OS'

# Anchor on the label field: the ESP path \EFI\SONiC-OS\grubx64.efi carries the
# label too, and a loose match also accepts the "SONiC" fallback-loader entry.
_SONIC_BOOT_ENTRY_RE = re.compile(
    r'^Boot([0-9A-Fa-f]{4})\*?\s+' + re.escape(SONIC_BOOT_LABEL) + r'(?:\s|$)')

# GPT partition type GUID of an EFI System Partition.
ESP_PARTTYPE = 'c12a7328-f81f-11d2-ba4b-00a0c93ec93b'
ESP_INIT_MOUNTPOINT = '/mnt/juniper-esp-init'


def _find_boot_id():
    """Return the Boot#### id (without the 'Boot' prefix) for the SONiC-OS entry."""
    try:
        result = subprocess.run(['/usr/bin/efibootmgr'], capture_output=True,
                                text=True, check=True)
    except (OSError, subprocess.CalledProcessError) as e:
        print(f"Error reading EFI configuration: {e}")
        return None

    for line in result.stdout.splitlines():
        match = _SONIC_BOOT_ENTRY_RE.match(line)
        if match:
            return match.group(1).upper()
    return None


def _find_esp():
    """Locate the EFI System Partition by GPT type GUID.

    Returns (partition_device, disk_device, partition_number), or a 3-tuple of
    None. Resolved at run time because the sd letters are not stable across a
    BIOS upgrade on this platform.
    """
    try:
        output = subprocess.check_output(
            ['lsblk', '-rno', 'PATH,PARTTYPE,PKNAME'], text=True)
    except (OSError, subprocess.CalledProcessError):
        print("Unable to enumerate partitions to locate the ESP")
        return None, None, None

    for line in output.splitlines():
        fields = line.split()
        if len(fields) < 3 or fields[1].lower() != ESP_PARTTYPE:
            continue
        part_dev = fields[0]
        try:
            with open(f"/sys/class/block/{os.path.basename(part_dev)}/partition") as f:
                return part_dev, f"/dev/{fields[2]}", f.read().strip()
        except IOError:
            continue

    return None, None, None


def _sonic_os_loader(esp_part):
    """Return the ESP-relative SONiC-OS loader path, e.g. /EFI/SONiC-OS/grubx64.efi.

    Globs grub*.efi exactly as the installer does rather than assuming a name,
    which also confirms the loader is really there before an entry is pointed
    at it. Returns None if the ESP cannot be read or holds no loader.
    """
    mountpoint = None
    mounted_here = False

    try:
        with open('/proc/mounts') as f:
            for line in f:
                fields = line.split()
                if (len(fields) >= 3 and fields[0] == esp_part
                        and fields[2] in ('vfat', 'msdos')):
                    mountpoint = fields[1]
                    break
    except IOError:
        pass

    if mountpoint is None:
        try:
            os.makedirs(ESP_INIT_MOUNTPOINT, exist_ok=True)
            subprocess.run(['mount', '-t', 'vfat', esp_part, ESP_INIT_MOUNTPOINT],
                           capture_output=True, text=True, check=True)
        except (OSError, subprocess.CalledProcessError) as e:
            print(f"Unable to mount the ESP {esp_part} ({e})")
            return None
        mountpoint = ESP_INIT_MOUNTPOINT
        mounted_here = True

    try:
        loaders = sorted(glob.glob(os.path.join(
            mountpoint, 'EFI', SONIC_BOOT_LABEL, 'grub*.efi')))
        if not loaders:
            print(f"No grub*.efi under EFI/{SONIC_BOOT_LABEL} on {esp_part}; "
                  "refusing to create a boot entry that points at nothing")
            return None
        return f"/EFI/{SONIC_BOOT_LABEL}/{os.path.basename(loaders[0])}"
    finally:
        if mounted_here:
            subprocess.run(['umount', mountpoint], capture_output=True)


def ensure_sonic_boot_entry():
    """Recreate the SONiC-OS EFI boot entry when the firmware has dropped it.

    A BIOS capsule upgrade rebuilds NVRAM from scratch: the named OS entry
    disappears and only auto-generated HDD/ETH entries remain. Those boot the
    ESP fallback loader, which lands the box in ONIE.
    """
    if not os.path.isdir('/sys/firmware/efi/efivars'):
        return

    if _find_boot_id() is not None:
        return

    print(f"No '{SONIC_BOOT_LABEL}' EFI boot entry found -- the platform "
          "firmware cleared it (a BIOS upgrade does this). Recreating.")

    esp_part, esp_disk, esp_partnum = _find_esp()
    if esp_part is None:
        print("Could not locate the EFI System Partition; unable to recreate "
              f"the '{SONIC_BOOT_LABEL}' boot entry")
        return

    loader = _sonic_os_loader(esp_part)
    if loader is None:
        return

    # --create also marks the entry active and prepends it to BootOrder.
    try:
        subprocess.run(['/usr/bin/efibootmgr', '--quiet', '--create',
                        '--label', SONIC_BOOT_LABEL,
                        '--disk', esp_disk, '--part', esp_partnum,
                        '--loader', loader],
                       capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError) as e:
        print(f"Failed to recreate the '{SONIC_BOOT_LABEL}' boot entry ({e})")
        return

    print(f"Recreated EFI boot entry '{SONIC_BOOT_LABEL}' -> {esp_disk} "
          f"part {esp_partnum} {loader}")


def set_next_boot():
    """Point EFI BootNext at the SONiC-OS entry."""
    try:
        result = subprocess.run(['/usr/bin/efibootmgr'], capture_output=True,
                                text=True, check=True)
    except (OSError, subprocess.CalledProcessError) as e:
        print(f"Error reading EFI configuration: {e}")
        return

    for line in result.stdout.splitlines():
        match = _SONIC_BOOT_ENTRY_RE.match(line)
        if match:
            boot_id = match.group(1).upper()
            try:
                subprocess.run(['/usr/bin/efibootmgr', '-n', boot_id],
                               capture_output=True, text=True, check=True)
            except (OSError, subprocess.CalledProcessError) as e:
                print(f"Error setting BootNext: {e}")
                return
            print(f"Set BootNext to {boot_id} ({SONIC_BOOT_LABEL})")
            return

    # Leave BootNext unset rather than falling back to BootCurrent: re-arming
    # whatever booted this time latches a wrong entry permanently.
    print(f"Unable to find the {SONIC_BOOT_LABEL} EFI entry; BootNext unchanged")


def get_cache_device():
    default_dev = "/dev/nvme0n1p2"
    try:
        result = subprocess.check_output(
            ["findmnt", "-nvo", "SOURCE", "/host"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        if result:
            return f"{result[:-1]}2"
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return default_dev


CACHE_MNT_DIR = "/mnt/onie"
CACHE_DEV = get_cache_device()
PLATFORM_CACHE_DIR = "/var/run/platform_cache"
CACHE_FILE_SOURCE = os.path.join(CACHE_MNT_DIR, "onie_syseeprom.cache")
CACHE_FILE_DEST = os.path.join(PLATFORM_CACHE_DIR, "onie_syseeprom.cache")
EEPROM_HEX = "/var/tmp/eeprom.hex"
EEPROM_BIN = "/var/tmp/eeprom_24c02.bin"
EEPROM_SIZE = 256  # 24C02 size


def copy_cache_file_and_unmount():
    mounted = False
    with open("/proc/mounts") as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == CACHE_MNT_DIR:
                mounted = True
                break

    if not mounted:
        os.makedirs(CACHE_MNT_DIR, exist_ok=True)
        print(f"Mounting {CACHE_DEV} to {CACHE_MNT_DIR}...")
        subprocess.run(["mount", CACHE_DEV, CACHE_MNT_DIR], check=True)
    else:
        print(f"{CACHE_MNT_DIR} is already mounted")

    os.makedirs(PLATFORM_CACHE_DIR, exist_ok=True)

    if os.path.isfile(CACHE_FILE_SOURCE):
        shutil.copy2(CACHE_FILE_SOURCE, CACHE_FILE_DEST)
    else:
        raise RuntimeError(f"Shadow EEPROM cache not found: {CACHE_FILE_SOURCE}")

    subprocess.run(["umount", CACHE_MNT_DIR], check=True)


def eeprom():
    time.sleep(2)
    copy_cache_file_and_unmount()

    if not os.path.isfile(CACHE_FILE_DEST):
        raise RuntimeError(f"Shadow EEPROM cache not found after copy: {CACHE_FILE_DEST}")

    with open(CACHE_FILE_DEST, "rb") as f:
        cache = f.read()

    memory = bytearray([0xFF] * EEPROM_SIZE)
    copy_len = min(len(cache), EEPROM_SIZE)
    memory[:copy_len] = cache[:copy_len]
    if len(cache) > EEPROM_SIZE:
        print(f"Warning: cache is {len(cache)} bytes; truncated to {EEPROM_SIZE}")

    with open(EEPROM_HEX, "w") as outf:
        for base in range(0, EEPROM_SIZE, 16):
            chunk = memory[base:base + 16]
            outf.write(f"{base:02x}: " + " ".join(f"{b:02x}" for b in chunk) + "\n")

    with open(EEPROM_BIN, "wb") as outf:
        outf.write(memory)

    print(f"Wrote {EEPROM_HEX} and {EEPROM_BIN} from {CACHE_FILE_DEST} (copied {copy_len} bytes)")

    eeprom_file = f'{device_info.get_path_to_platform_dir()}/plugins/eeprom_data.py'
    if os.path.isfile(eeprom_file):
        try:
            subprocess.call(['python3', eeprom_file])
        except OSError as e:
            print(f"Error running eeprom_data.py: {e}")


def resize_var_log_partition():
    status, df_output = log_os_system("df -h /var/log", 1)
    if status == 0:
        print(f"Current /var/log status:\n{df_output}")

    status, losetup_output = log_os_system("losetup | grep var-log", 0)
    if status != 0:
        print("Warning: Could not find var-log loop device")
        return False

    loop_device = None
    for line in losetup_output.strip().split('\n'):
        if 'var-log.ext4' in line:
            parts = line.split()
            if parts:
                loop_device = parts[0]
                break

    if not loop_device:
        print("Error: Could not identify var-log loop device")
        return False

    var_log_path = "/host/disk-img/var-log.ext4"
    if not os.path.exists(var_log_path):
        print(f"Error: {var_log_path} does not exist")
        return False

    if os.path.getsize(var_log_path) >= 32 * 1024 * 1024 * 1024:
        print("var-log.ext4 is already 32G or larger, skipping resize")
        return True

    for cmd in [
        f"truncate -s 32G {var_log_path}",
        f"losetup -c {loop_device}",
        f"resize2fs {loop_device}",
    ]:
        status, _ = log_os_system(cmd, 1)
        if status != 0:
            print(f"Error: command failed: {cmd}")
            return False

    print("Successfully resized /var/log partition to 32G")
    return True


def fw_copy():
    platform = device_info.get_platform()
    cmd = f"cp -r /usr/share/sonic/device/{platform}/bin/* /usr/bin/"
    log_os_system(cmd, 1)


def set_base_mac():
    status, macAddress = getstatusoutput_noshell(["decode-syseeprom", "-m", "0x24"])
    if status:
        print("Error: Could not retrieve BASE MAC Address from EEPROM")
        return
    cmd = f"ifconfig eth0 hw ether {macAddress}"
    status, _ = log_os_system(cmd, 1)
    if status:
        print("Error: Could not set base MAC address on eth0")


def main():
    # The entry has to exist before BootNext can point at it.
    ensure_sonic_boot_entry()
    set_next_boot()
    resize_var_log_partition()
    eeprom()
    fw_copy()
    set_base_mac()


if __name__ == '__main__':
    main()
