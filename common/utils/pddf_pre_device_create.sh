#!/bin/bash
#
# PDDF pre-device-create hook.
#
# pddf_util.py device_install() runs /usr/local/bin/pddf_pre_device_create.sh
# (if present) after the kernel modules from std_kos/pddf_kos/custom_kos have
# been loaded and before create_pddf_devices() walks pddf-device.json.
#
# PDDF only ever calls this one fixed path, so the hook lives in the shared
# utils/ directory (installed into sonic-platform-juniper-common) and dispatches
# on onie_platform.
# Platforms with no pre-device-create step fall through to the no-op default.

set -u

log() {
    logger -t "pddf_pre_device_create" "$@"
}

. /host/machine.conf 2>/dev/null

case "${onie_platform:-}" in
    x86_64-juniper_qfx5230-r0)
        exec /usr/bin/python3 /usr/local/bin/qfx5230_pre_device_create.py
        ;;
    x86_64-juniper_qfx5241-r0)
        exec /usr/bin/python3 /usr/local/bin/qfx5241_pre_device_create.py
        ;;
    *)
        log "No pre-device-create step for ${onie_platform:-unknown}, skipping"
        exit 0
        ;;
esac
