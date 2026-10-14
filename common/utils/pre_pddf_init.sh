#!/bin/bash
# Pre-PDDF initialization dispatcher for Juniper PDDF platforms
#
# Runs BEFORE pddf_util.py install (via ExecStartPre in
# pddf-platform-init.service).  Detects the current platform
# from machine.conf and calls the platform-specific init script.

log() {
    logger -t "pre_pddf_init" "$@"
}

# Determine platform
. /host/machine.conf 2>/dev/null
if [ -z "$onie_platform" ]; then
    log -p user.err "Cannot determine platform (onie_platform not set)"
    exit 1
fi

case "$onie_platform" in
    x86_64-juniper_qfx5252-r0)
        PLATFORM_INIT="/usr/local/bin/qfx5252_platform_init.py"
        ;;
    x86_64-juniper_aruba_cx8325h-r0)
        PLATFORM_INIT="/usr/local/bin/cx8325h_platform_init.py"
        ;;
    *)
        log "No platform-specific init for $onie_platform, skipping"
        exit 0
        ;;
esac

if [ -f "$PLATFORM_INIT" ]; then
    log "Running platform initialization for $onie_platform: $PLATFORM_INIT"
    "$PLATFORM_INIT"
    rc=$?
    if [ $rc -ne 0 ]; then
        log -p user.warning "Platform init exited with code $rc"
    else
        log "Platform initialization completed successfully."
    fi
else
    log -p user.err "Platform init script not found: $PLATFORM_INIT"
fi
