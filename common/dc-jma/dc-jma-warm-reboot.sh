#!/bin/bash
# dc-jma-warm-reboot.sh - Warm/Fast reboot hook for dc-jma
# This script is called during warm/fast reboot to save state

CONTAINER_NAME="dc-jma"
WARM_DIR="/host/warmboot"
DC_JMA_WARM_DIR="${WARM_DIR}/dc-jma"

# Registration file locations
MIST_CONFIG_DIR="/config/mist/jma"
REG_FILES=("EPtermCA.crt" "mist_reg_code.txt" "reg.json")

save_state() {
    echo "dc-jma: Saving state for warm reboot..."
    
    # Create warm boot directory
    mkdir -p "${DC_JMA_WARM_DIR}"
    
    # Save registration files
    for f in "${REG_FILES[@]}"; do
        if [[ -f "${MIST_CONFIG_DIR}/${f}" ]]; then
            cp -f "${MIST_CONFIG_DIR}/${f}" "${DC_JMA_WARM_DIR}/"
            echo "dc-jma: Saved ${f}"
        fi
    done
    
    # Mark state as saved
    touch "${DC_JMA_WARM_DIR}/.state_saved"
    
    echo "dc-jma: State saved for warm reboot"
}

restore_state() {
    echo "dc-jma: Restoring state from warm reboot..."
    
    if [[ ! -d "${DC_JMA_WARM_DIR}" ]]; then
        echo "dc-jma: No warm boot state directory found"
        return 1
    fi
    
    # Restore registration files
    mkdir -p "${MIST_CONFIG_DIR}"
    for f in "${REG_FILES[@]}"; do
        if [[ -f "${DC_JMA_WARM_DIR}/${f}" ]]; then
            cp -f "${DC_JMA_WARM_DIR}/${f}" "${MIST_CONFIG_DIR}/"
            echo "dc-jma: Restored ${f}"
        fi
    done
    
    echo "dc-jma: State restored from warm reboot"
}

cleanup_state() {
    echo "dc-jma: Cleaning up warm boot state..."
    rm -rf "${DC_JMA_WARM_DIR}"
}

case "$1" in
    save)
        save_state
        ;;
    restore)
        restore_state
        ;;
    cleanup)
        cleanup_state
        ;;
    *)
        echo "Usage: $0 {save|restore|cleanup}"
        exit 1
        ;;
esac
