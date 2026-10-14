#!/bin/bash
set -euo pipefail

# dc-jma-upgrade.sh - Field upgrade script for Juniper Mist Agent container
#
# Usage:  dc-jma-upgrade.sh [<image.tgz>]
#
# If no argument is given, looks for the image at the default location:
#   /config/mist/jma/dc-jma-sonic.tgz
#
# One-step field upgrade.  Accepts a docker image tarball, loads it,
# and restarts the service through the normal systemd lifecycle
# (stop → start).  Rolls back on failure.
#
# Exit codes:
#   0 — success
#   1 — upgrade failed, rollback succeeded
#   2 — usage error / upgrade failed AND rollback failed

# Must run as root
if [[ $EUID -ne 0 ]]; then
    echo "Error: This script must be run as root (use sudo)." >&2
    exit 2
fi

DOCKER_IMAGE="docker-sonic-dc-jma"
DOCKERNAME="dc-jma"
DEFAULT_IMAGE_DIR="/config/mist/jma"
DEFAULT_IMAGE_FILE="${DEFAULT_IMAGE_DIR}/dc-jma-sonic.tgz"

debug() {
    /usr/bin/logger -t dc-jma "$1"
}

info() {
    echo "==> $1"
    /usr/bin/logger -t dc-jma "UPGRADE: $1"
}

err() {
    echo "Error: $1" >&2
    /usr/bin/logger -t dc-jma "UPGRADE ERROR: $1"
}

# ── Compare semver strings (major.minor.patch) ─────────────────────
# Returns via global SEMVER_CMP: -1 (a < b), 0 (a == b), 1 (a > b)
SEMVER_CMP=0
compare_semver() {
    local a="$1" b="$2"
    local a_major a_minor a_patch b_major b_minor b_patch
    IFS='.' read -r a_major a_minor a_patch <<< "$a"
    IFS='.' read -r b_major b_minor b_patch <<< "$b"
    a_major=${a_major:-0}; a_minor=${a_minor:-0}; a_patch=${a_patch:-0}
    b_major=${b_major:-0}; b_minor=${b_minor:-0}; b_patch=${b_patch:-0}

    if (( a_major != b_major )); then
        (( a_major > b_major )) && SEMVER_CMP=1 || SEMVER_CMP=-1
    elif (( a_minor != b_minor )); then
        (( a_minor > b_minor )) && SEMVER_CMP=1 || SEMVER_CMP=-1
    elif (( a_patch != b_patch )); then
        (( a_patch > b_patch )) && SEMVER_CMP=1 || SEMVER_CMP=-1
    else
        SEMVER_CMP=0
    fi
}

# ── Resolve image file ─────────────────────────────────────────────
USED_DEFAULT=false
if [[ -n "${1:-}" ]]; then
    IMAGE_FILE="$1"
else
    IMAGE_FILE="${DEFAULT_IMAGE_FILE}"
    USED_DEFAULT=true
    info "No image specified, using default: ${IMAGE_FILE}"
fi

if [[ ! -f "${IMAGE_FILE}" ]]; then
    if [[ "${USED_DEFAULT}" == true ]]; then
        err "No image found at default location: ${IMAGE_FILE}"
        echo "Copy the upgrade tarball to ${DEFAULT_IMAGE_DIR}/ or provide a path:" >&2
        echo "  Usage: $0 [<image.tgz>]" >&2
    else
        err "File not found: ${IMAGE_FILE}"
    fi
    exit 1
fi

# Validate the tarball contains a Docker image
info "Validating image tarball..."
if ! tar -tzf "${IMAGE_FILE}" 2>/dev/null | grep -q 'manifest.json' \
   && ! tar -tf "${IMAGE_FILE}" 2>/dev/null | grep -q 'manifest.json'; then
    err "${IMAGE_FILE} does not appear to be a Docker image tarball (no manifest.json)."
    exit 1
fi

# ── Version comparison ─────────────────────────────────────────────
# Read the currently installed version from OCI labels
CURRENT_VERSION=$(docker inspect "${DOCKER_IMAGE}:latest" \
    --format '{{index .Config.Labels "org.opencontainers.image.version"}}' 2>/dev/null) || true

# Extract the new image's version label directly from the tarball
NEW_VERSION=""
if command -v jq >/dev/null 2>&1; then
    CONFIG_FILE=$(tar -xf "${IMAGE_FILE}" -O manifest.json 2>/dev/null \
        | jq -r '.[0].Config // empty' 2>/dev/null) || true
    if [[ -n "${CONFIG_FILE}" ]]; then
        NEW_VERSION=$(tar -xf "${IMAGE_FILE}" -O "${CONFIG_FILE}" 2>/dev/null \
            | jq -r '.config.Labels["org.opencontainers.image.version"] // empty' 2>/dev/null) || true
    fi
fi

if [[ -n "${CURRENT_VERSION}" && -n "${NEW_VERSION}" ]]; then
    info "Installed version: ${CURRENT_VERSION}"
    info "New image version: ${NEW_VERSION}"

    compare_semver "${NEW_VERSION}" "${CURRENT_VERSION}"

    if (( SEMVER_CMP == 0 )); then
        info "New image is the same version as currently installed (${CURRENT_VERSION})."
        read -r -p "Proceed with reinstall? [y/N]: " answer
        if [[ ! "${answer}" =~ ^[Yy]$ ]]; then
            info "Upgrade cancelled."
            exit 0
        fi
    elif (( SEMVER_CMP < 0 )); then
        info "WARNING: New image (${NEW_VERSION}) is older than installed version (${CURRENT_VERSION})."
        read -r -p "Proceed with downgrade? [y/N]: " answer
        if [[ ! "${answer}" =~ ^[Yy]$ ]]; then
            info "Upgrade cancelled."
            exit 0
        fi
    fi
elif [[ -n "${CURRENT_VERSION}" ]]; then
    info "Installed version: ${CURRENT_VERSION}"
    info "New image version: unknown (no version label)"
fi

# Save the old image ID for rollback and cleanup.
OLD_IMAGE_ID=$(docker images --quiet --no-trunc "${DOCKER_IMAGE}:latest" 2>/dev/null) || true

# Back up the old image to a temp file
OLD_IMAGE_BACKUP=""
if [[ -n "${OLD_IMAGE_ID}" ]]; then
    OLD_IMAGE_BACKUP=$(mktemp /tmp/dc-jma-rollback-XXXXXX.tar)
    if ! docker save -o "${OLD_IMAGE_BACKUP}" "${DOCKER_IMAGE}:latest" 2>/dev/null; then
        err "Could not back up old image. Aborting upgrade."
        rm -f "${OLD_IMAGE_BACKUP}"
        exit 1
    fi
fi

# Ensure rollback backup is cleaned up on any exit from this point
upgrade_cleanup() {
    [[ -n "${OLD_IMAGE_BACKUP:-}" ]] && rm -f "${OLD_IMAGE_BACKUP}" || true
}
trap 'upgrade_cleanup' EXIT

# Track whether rollback itself fails
ROLLBACK_FAILED=false

upgrade_rollback() {
    # Ensure systemd is in a clean state before attempting restart.
    systemctl stop dc-jma 2>/dev/null || true
    systemctl reset-failed dc-jma 2>/dev/null || true

    if [[ -n "${OLD_IMAGE_BACKUP}" && -f "${OLD_IMAGE_BACKUP}" ]]; then
        info "Rolling back to previous image..."
        docker rm -f "${DOCKERNAME}" 2>/dev/null || true
        docker load --input "${OLD_IMAGE_BACKUP}" 2>/dev/null || true
        if ! systemctl start dc-jma 2>/dev/null; then
            err "Rollback start failed — manual intervention required."
            ROLLBACK_FAILED=true
            return 1
        fi
        info "Rolled back to ${OLD_IMAGE_ID}."
    elif [[ -n "${OLD_IMAGE_ID}" ]]; then
        info "Attempting best-effort rollback..."
        docker rm -f "${DOCKERNAME}" 2>/dev/null || true
        docker tag "${OLD_IMAGE_ID}" "${DOCKER_IMAGE}:latest" 2>/dev/null || true
        if ! systemctl start dc-jma 2>/dev/null; then
            err "Rollback start failed — manual intervention required."
            ROLLBACK_FAILED=true
            return 1
        fi
        info "Best-effort rollback to ${OLD_IMAGE_ID}."
    else
        err "No previous image to roll back to."
        ROLLBACK_FAILED=true
        return 1
    fi
}

info "Starting upgrade from ${IMAGE_FILE} (old image: ${OLD_IMAGE_ID:-none})."

info "Stopping dc-jma service..."
systemctl stop dc-jma 2>/dev/null || /usr/local/bin/dc-jma.sh stop

if docker ps -q -f "name=^${DOCKERNAME}$" | grep -q .; then
    err "dc-jma container is still running after stop attempt."
    exit 1
fi

info "Loading new docker image from ${IMAGE_FILE}..."
if ! LOAD_OUTPUT=$(docker load --input "${IMAGE_FILE}" 2>&1); then
    err "docker load failed for ${IMAGE_FILE}."
    echo "${LOAD_OUTPUT}" >&2
    upgrade_rollback
    [[ "${ROLLBACK_FAILED}" == true ]] && exit 2 || exit 1
fi
echo "${LOAD_OUTPUT}"
info "Loaded new image from ${IMAGE_FILE}."

# docker load prints "Loaded image: <name>:<tag>" — parse it.
# If the loaded image name differs from DOCKER_IMAGE, re-tag it
# so start (which uses DOCKER_IMAGE:latest) finds the right image.
LOADED_IMAGE=$(echo "${LOAD_OUTPUT}" | grep -oP '(?<=Loaded image: ).+' | tail -1) || true
if [[ -n "${LOADED_IMAGE}" && "${LOADED_IMAGE}" != "${DOCKER_IMAGE}:latest" ]]; then
    debug "Loaded image '${LOADED_IMAGE}' differs from expected '${DOCKER_IMAGE}:latest' — re-tagging."
    if ! docker tag "${LOADED_IMAGE}" "${DOCKER_IMAGE}:latest"; then
        err "Failed to re-tag ${LOADED_IMAGE} as ${DOCKER_IMAGE}:latest"
        upgrade_rollback
        [[ "${ROLLBACK_FAILED}" == true ]] && exit 2 || exit 1
    fi
    info "Re-tagged ${LOADED_IMAGE} → ${DOCKER_IMAGE}:latest"
fi

NEW_IMAGE_ID=$(docker images --quiet --no-trunc "${DOCKER_IMAGE}:latest" 2>/dev/null) || true

# Skip restart cycle if the loaded image is identical to what was running
if [[ -n "${OLD_IMAGE_ID}" && "${NEW_IMAGE_ID}" == "${OLD_IMAGE_ID}" ]]; then
    info "Image is identical to current version (${OLD_IMAGE_ID}). Restarting service."
    docker rm -f "${DOCKERNAME}" 2>/dev/null || true
    systemctl start dc-jma 2>/dev/null || /usr/local/bin/dc-jma.sh start
    info "Service restarted (no image change)."
    exit 0
fi

# Remove old container so it gets recreated with the new image
docker rm -f "${DOCKERNAME}" 2>/dev/null || true

info "Starting dc-jma service with new image..."
if ! systemctl start dc-jma 2>/dev/null; then
    err "Failed to start with new image ${NEW_IMAGE_ID}."
    upgrade_rollback
    [[ "${ROLLBACK_FAILED}" == true ]] && exit 2 || exit 1
fi

# Poll for up to 60 seconds to verify the container is running
info "Waiting for container to come up..."
UPGRADE_OK=false
for i in $(seq 1 12); do
    if docker ps -q -f "name=^${DOCKERNAME}$" | grep -q .; then
        UPGRADE_OK=true
        break
    fi
    sleep 5
done

if [[ "${UPGRADE_OK}" != true ]]; then
    err "Container is not running after upgrade (waited 60s)."
    info "Last 30 lines of container logs:"
    docker logs --tail 30 "${DOCKERNAME}" 2>&1 || true
    upgrade_rollback
    [[ "${ROLLBACK_FAILED}" == true ]] && exit 2 || exit 1
fi

# Success — clean up old image
if [[ -n "${OLD_IMAGE_ID}" && "${OLD_IMAGE_ID}" != "${NEW_IMAGE_ID}" ]]; then
    info "Removing old image ${OLD_IMAGE_ID}..."
    docker rmi "${OLD_IMAGE_ID}" 2>/dev/null || true
fi

info "Upgrade complete (new image: ${NEW_IMAGE_ID}). Check status with: systemctl status dc-jma"

# Clean up the tarball if we used the default location
if [[ "${USED_DEFAULT}" == true ]]; then
    rm -f "${IMAGE_FILE}"
    info "Removed upgrade tarball from ${DEFAULT_IMAGE_DIR}/"
fi
