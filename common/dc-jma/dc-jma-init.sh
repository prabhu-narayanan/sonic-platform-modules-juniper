#!/bin/bash
# dc-jma-init.sh - Container initialization script
# This script runs inside the dc-jma container at startup

set -e

# Generate supervisord config if using templates
mkdir -p /etc/supervisor/conf.d/

# Wait for database to be ready
wait_for_database() {
    local max_wait=60
    local count=0
    
    echo "Waiting for database connection..."
    while [ $count -lt $max_wait ]; do
        if sonic-db-cli PING 2>/dev/null | grep -q PONG; then
            echo "Database is ready"
            return 0
        fi
        sleep 1
        count=$((count + 1))
    done
    
    echo "Warning: Database not available after ${max_wait} seconds"
    return 1
}

# Update feature status in STATE_DB
update_feature_state() {
    if command -v sonic-db-cli &> /dev/null; then
        sonic-db-cli STATE_DB HSET "FEATURE|dc-jma" "state" "running" 2>/dev/null || true
        sonic-db-cli STATE_DB HSET "FEATURE|dc-jma" "up_status" "true" 2>/dev/null || true
    fi
}

# Main initialization
main() {
    echo "dc-jma container initialization starting..."
    
    # Set up logging to syslog
    if [ -f /etc/rsyslog.conf ]; then
        echo "Configuring rsyslog..."
    fi
    
    # Wait for database (non-blocking - continue even if unavailable)
    wait_for_database || true
    
    # Update feature state
    update_feature_state
    
    echo "dc-jma container initialization complete"
}

main "$@"
