#!/bin/bash

# dc-jma.sh - SONiC container control script for Juniper Mist Agent
# Follows the docker_image_ctl.j2 pattern used by native SONiC containers.
# Supports: start, wait, stop, kill, status

DOCKER_IMAGE="docker-sonic-dc-jma"
DOCKERNAME="dc-jma"
CONTAINER_NAME="dc-jma"

# SONiC tools — use correct paths (/usr/local/bin, not /usr/bin)
SONIC_DB_CLI="sonic-db-cli"
SONIC_CFGGEN="sonic-cfggen"

# Configuration paths
MIST_CONFIG_DIR="/config/mist/jma"
MIST_HOST_DIR="/host/config/mist/jma"
# Files to persist to host on stop (includes reg.json for backup)
PERSIST_FILES=("root_cert.pem" "mist_reg_code.txt" "reg.json")
# Files to restore from host on pre (reg.json excluded — JMA regenerates it from mist_reg_code)
RESTORE_FILES=("root_cert.pem" "mist_reg_code.txt")

# ── Helper functions ────────────────────────────────────────────────

debug() {
    /usr/bin/logger -t dc-jma "$1"
}

get_platform() {
    local p
    p=$($SONIC_CFGGEN -H -v DEVICE_METADATA.localhost.platform 2>/dev/null) || true
    echo "${p:-unknown}"
}

get_hwsku() {
    $SONIC_CFGGEN -d -v 'DEVICE_METADATA["localhost"]["hwsku"]' 2>/dev/null || true
}

is_feature_enabled() {
    local state
    state=$($SONIC_DB_CLI CONFIG_DB HGET "FEATURE|dc-jma" "state" 2>/dev/null) || true
    [[ "$state" == "enabled" || "$state" == "always_enabled" ]]
}

getBootType() {
    case "$(cat /proc/cmdline 2>/dev/null)" in
        *SONIC_BOOT_TYPE=warm*)     echo "warm" ;;
        *SONIC_BOOT_TYPE=fastfast*) echo "fastfast" ;;
        *SONIC_BOOT_TYPE=express*)  echo "express" ;;
        *SONIC_BOOT_TYPE=fast*|*fast-reboot*) echo "fast" ;;
        *) echo "cold" ;;
    esac
}

check_warm_boot() {
    local sys svc
    sys=$($SONIC_DB_CLI STATE_DB hget "WARM_RESTART_ENABLE_TABLE|system" enable 2>/dev/null) || true
    svc=$($SONIC_DB_CLI STATE_DB hget "WARM_RESTART_ENABLE_TABLE|${CONTAINER_NAME}" enable 2>/dev/null) || true
    [[ "$sys" == "true" || "$svc" == "true" ]]
}

check_fast_boot() {
    local fb
    fb=$($SONIC_DB_CLI STATE_DB hget "FAST_RESTART_ENABLE_TABLE|system" enable 2>/dev/null) || true
    [[ "$fb" == "true" ]]
}

getMountPoint() {
    echo "$1" | python3 -c "
import sys, json, os
mnts = [x for x in json.load(sys.stdin)[0]['Mounts'] if x['Destination'] == '/usr/share/sonic/hwsku']
print('' if len(mnts) == 0 else os.path.abspath(mnts[0]['Source']))
" 2>/dev/null
}

# ── Pre/post start actions ──────────────────────────────────────────

preStartAction() {
    debug "preStartAction: Preparing registration files"

    # Ensure config directories exist
    mkdir -p "${MIST_CONFIG_DIR}" "${MIST_HOST_DIR}"

    # Restore only root_cert.pem and mist_reg_code.txt from host backup
    # if they are missing from the working directory.
    # reg.json is never restored — JMA regenerates it from mist_reg_code.txt.
    for f in "${RESTORE_FILES[@]}"; do
        if [[ ! -f "${MIST_CONFIG_DIR}/${f}" ]] && [[ -f "${MIST_HOST_DIR}/${f}" ]]; then
            cp -f "${MIST_HOST_DIR}/${f}" "${MIST_CONFIG_DIR}/"
            debug "preStartAction: Restored ${f} from host"
        fi
    done
}

postStartAction() {
    debug "postStartAction: Container started"
    # Update DNS for containers (same as native SONiC)
    /etc/resolvconf/update-libc.d/update-containers ${DOCKERNAME} 2>/dev/null &
}

# ── Container lifecycle ─────────────────────────────────────────────

start() {
    BOOT_TYPE=$(getBootType)
    PLATFORM=$(get_platform)
    HWSKU=$(get_hwsku)

    debug "Starting dc-jma (boot=$BOOT_TYPE platform=$PLATFORM hwsku=$HWSKU)"

    if ! is_feature_enabled; then
        debug "Feature dc-jma is disabled in CONFIG_DB, not starting"
        exit 0
    fi

    # Parse ASIC config for multi-ASIC awareness
    local ASIC_CONF="/usr/share/sonic/device/$PLATFORM/asic.conf"
    local NUM_ASIC=1
    if [ -f "$ASIC_CONF" ]; then
        source "$ASIC_CONF"
    fi

    # Syslog target IP
    local SYSLOG_TARGET_IP="127.0.0.1"
    if [[ $NUM_ASIC -gt 1 ]]; then
        SYSLOG_TARGET_IP=$(docker network inspect bridge --format='{{(index .IPAM.Config 0).Gateway}}')
    fi

    # HWSKU mount path
    local MOUNTPATH="/usr/share/sonic/device/$PLATFORM/$HWSKU"

    # Redis mount
    local REDIS_MNT="-v /var/run/redis:/var/run/redis:rw"

    # Multi-ASIC: mount additional redis namespace dirs for global containers
    local SONIC_DB_GLOBAL_JSON="/var/run/redis/sonic-db/database_global.json"
    if [ -f "$SONIC_DB_GLOBAL_JSON" ]; then
        local redis_dir_list
        redis_dir_list=$(/usr/bin/python3 -c "
import sys, os, json
f = open(sys.argv[1])
d = os.path.dirname(sys.argv[1])
data = json.load(f)
print(' '.join([os.path.normpath(d+'/'+e['include']).partition('sonic-db')[0]
                for e in data['INCLUDES'] if 'namespace' in e or 'container_name' in e]))
f.close()
" "$SONIC_DB_GLOBAL_JSON" 2>/dev/null) || true
        for rdir in $redis_dir_list; do
            REDIS_MNT="$REDIS_MNT -v $rdir:$rdir:rw"
        done
    fi

    # Check if container already exists with correct HWSKU
    local DOCKERCHECK
    DOCKERCHECK=$(docker inspect --type container ${DOCKERNAME} 2>/dev/null)
    if [ "$?" -eq "0" ]; then
        local DOCKERMOUNT
        DOCKERMOUNT=$(getMountPoint "$DOCKERCHECK")
        if [ "x$DOCKERMOUNT" == "x$MOUNTPATH" ]; then
            debug "Starting existing ${DOCKERNAME} container"
            preStartAction
            /usr/local/bin/container start ${DOCKERNAME} 2>/dev/null || docker start ${DOCKERNAME}
            postStartAction
            return $?
        fi
        # HWSKU changed — recreate
        debug "Removing obsolete ${DOCKERNAME} container (old HWSKU: $DOCKERMOUNT)"
        docker rm -f ${DOCKERNAME}
    fi

    debug "Creating new ${DOCKERNAME} container"

    preStartAction

    docker create \
        --name=${DOCKERNAME} \
        --net=host \
        --privileged \
        --uts=host \
        --log-opt max-size=2M \
        --log-opt max-file=5 \
        --tmpfs /var/log/supervisor:rw \
        --tmpfs /tmp \
        --tmpfs /var/tmp \
        -v /etc/sonic:/etc/sonic:ro \
        -v /etc/localtime:/etc/localtime:ro \
        -v /host/warmboot:/var/warmboot \
        -v /host:/host:rw \
        -v /var/log:/var/log:rw \
        -v /var/core:/var/core:rw \
        $REDIS_MNT \
        -v /var/run/redis-chassis:/var/run/redis-chassis:ro \
        -v /usr/share/sonic/device/$PLATFORM/$HWSKU:/usr/share/sonic/hwsku:ro \
        -v /usr/share/sonic/device/$PLATFORM:/usr/share/sonic/platform:ro \
        -v /etc/fips/fips_enable:/etc/fips/fips_enable:ro \
        -v /usr/share/sonic/templates/rsyslog-container.conf.j2:/usr/share/sonic/templates/rsyslog-container.conf.j2:ro \
        -v ${MIST_CONFIG_DIR}:${MIST_CONFIG_DIR}:rw \
        -v /dev:/dev:ro \
        -v /sys:/sys:ro \
        -v /run/dbus:/run/dbus:ro \
        --env "NAMESPACE_ID"="" \
        --env "NAMESPACE_PREFIX"="asic" \
        --env "NAMESPACE_COUNT"="$NUM_ASIC" \
        --env "DEV"="" \
        --env "CONTAINER_NAME"=$DOCKERNAME \
        --env "SYSLOG_TARGET_IP"=$SYSLOG_TARGET_IP \
        --env "PLATFORM"=$PLATFORM \
        --env "RUNTIME_OWNER"=local \
        --env "IMAGE_VERSION"="${IMAGE_VERSION:-}" \
        -e JMA_SONIC_MODE=1 \
        -e JMA_JMD_SIMPLE=1 \
        -e JMA_JMD_PSU_WATCHER=1 \
        -e JMA_TELEMETRY_JSON=1 \
        -e JMA_LOG_TELEMETRY_ENVELOPE=1 \
        -e JMA_DISABLE_NETCONF=1 \
        -e JMA_NO_JMD_RESTART_AFTER_CLOUD=1 \
        -e JMA_FRU_SYSLOG_MODE=full \
        ${DOCKER_IMAGE}:latest \
        || {
            echo "Failed to docker create ${DOCKERNAME}" >&2
            exit 4
        }

    /usr/local/bin/container start ${DOCKERNAME} 2>/dev/null || docker start ${DOCKERNAME}
    postStartAction
}

wait() {
    # Loop so that a "docker restart" does not cause systemd to consider the service dead.
    while true; do
        /usr/local/bin/container wait ${DOCKERNAME} 2>/dev/null || docker wait ${DOCKERNAME} || true
        # Give a moment for docker restart to bring the container back
        sleep 2
        if ! docker ps -q -f "name=^/?${DOCKERNAME}$" | grep -q .; then
            # Container is genuinely stopped — exit so systemd can act
            debug "wait: Container ${DOCKERNAME} has exited"
            break
        fi
        debug "wait: Container ${DOCKERNAME} restarted, re-entering wait"
    done
}

stop() {
    debug "Stopping ${DOCKERNAME} container"

    # Persist registration files before stopping
    if docker ps -q -f "name=^/?${DOCKERNAME}$" | grep -q .; then
        mkdir -p "${MIST_HOST_DIR}"
        for f in "${PERSIST_FILES[@]}"; do
            if [[ -f "${MIST_CONFIG_DIR}/${f}" ]]; then
                if cp -f "${MIST_CONFIG_DIR}/${f}" "${MIST_HOST_DIR}/"; then
                    debug "Persisted ${f} to host"
                else
                    debug "FAILED to cp ${f}: $?"
                fi
            else
                debug "Skip ${f}: not found at ${MIST_CONFIG_DIR}/${f}"
            fi
        done
    fi

    local cid
    cid=$(docker ps --filter "name=^/?${DOCKERNAME}$" --quiet)
    if [ -z "$cid" ]; then
        debug "Container ${DOCKERNAME} is not running"
    else
        /usr/local/bin/container stop ${DOCKERNAME} 2>/dev/null || docker stop ${DOCKERNAME}
    fi

    debug "Container ${DOCKERNAME} stopped"
}

restart() {
    if ! docker ps -q -f "name=^/?${DOCKERNAME}$" | grep -q .; then
        debug "restart: Container not running, performing full start"
        start
        return $?
    fi

    debug "Restarting ${DOCKERNAME} container"

    # Persist registration files before restart
    mkdir -p "${MIST_HOST_DIR}"
    for f in "${PERSIST_FILES[@]}"; do
        if [[ -f "${MIST_CONFIG_DIR}/${f}" ]]; then
            if cp -f "${MIST_CONFIG_DIR}/${f}" "${MIST_HOST_DIR}/"; then
                debug "Persisted ${f} to host"
            else
                debug "FAILED to cp ${f}: $?"
            fi
        else
            debug "Skip ${f}: not found at ${MIST_CONFIG_DIR}/${f}"
        fi
    done

    docker restart ${DOCKERNAME}
    postStartAction
}

kill() {
    /usr/local/bin/container kill ${DOCKERNAME} 2>/dev/null || docker kill ${DOCKERNAME}
}

status() {
    if docker ps -q -f "name=^/?${DOCKERNAME}$" | grep -q .; then
        echo "${DOCKERNAME} is running"
        docker ps -f "name=^/?${DOCKERNAME}$"
        return 0
    else
        echo "${DOCKERNAME} is not running"
        return 1
    fi
}

# ── Read SONiC immutable variables ──────────────────────────────────
[ -f /etc/sonic/sonic-environment ] && . /etc/sonic/sonic-environment

case "$1" in
    start|wait|stop|restart|kill|status)
        $1
        ;;
    *)
        echo "Usage: $0 {start|wait|stop|restart|kill|status}"
        exit 1
        ;;
esac
