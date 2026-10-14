#!/bin/bash
# ensure_epterm.sh — Add epterm entry to /etc/hosts for Mist Agent TLS
#
# Reads the epterm IP from CONFIG_DB DC_JMA|config "epterm_ip" field.
# Falls back to 10.87.95.11 if the DB is unreachable or the field is empty.
#
# Invoked by the platform package postinst script and can be re-run
# at any time to pick up a changed epterm_ip value.

set -e

FALLBACK_IP="10.87.95.11"

# Query CONFIG_DB for the configured epterm IP (DC_JMA|config table)
EPTERM_IP=""
if command -v sonic-db-cli &>/dev/null; then
    EPTERM_IP=$(sonic-db-cli CONFIG_DB HGET "DC_JMA|config" "epterm_ip" 2>/dev/null) || true
fi

# Use fallback if DB returned empty or is unavailable
if [ -z "$EPTERM_IP" ]; then
    echo "[dc-jma] epterm_ip not set in CONFIG_DB, using fallback $FALLBACK_IP"
    EPTERM_IP="$FALLBACK_IP"
fi

[ -f /etc/hosts ] || touch /etc/hosts

# Remove any existing epterm entry (IP may have changed)
sed -i '/[[:space:]]epterm\b/d' /etc/hosts

echo "$EPTERM_IP     epterm" >> /etc/hosts
