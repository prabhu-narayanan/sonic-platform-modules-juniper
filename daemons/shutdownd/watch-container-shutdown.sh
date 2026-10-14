#!/bin/bash
# Watch /host/reboot-cause for a shutdown request file

WATCH_DIR="/host/reboot-cause"
FLAG_FILE="shutdown_request"
LAST_REASON_FILE="/var/tmp/last-shutdown-reason"
TAG="shutdown-request-watcher"

# In case directory doesn't exist
mkdir -p "$WATCH_DIR"

# If previous shutdown reason exists, log it
if [[ -f "$LAST_REASON_FILE" ]]; then
    LAST_REASON=$(<"$LAST_REASON_FILE")
    logger -t "$TAG" -p user.info "System startup detected. Previous shutdown reason: '$LAST_REASON'"
    rm -f "$LAST_REASON_FILE"
else
    logger -t "$TAG" -p user.info "System startup detected. No previous shutdown reason recorded."
fi

logger -t "$TAG" -p user.info "Started polling $WATCH_DIR for shutdown requests from pmon docker..."

while true; do
    if [[ -f "$WATCH_DIR/$FLAG_FILE" ]]; then
	# Read the reason for shutdown (trim whitespace/newlines)
        REASON=$(tr -d '\r' < "$WATCH_DIR/$FLAG_FILE" | xargs)

        if [[ -z "$REASON" ]]; then
            REASON="No reason provided"
        fi

	logger -t "$TAG" -p user.notice "Shutdown requested. Reason: '$REASON'"
         
        # Store reason for next boot
        echo "$REASON" > "$LAST_REASON_FILE"

        rm -f "$WATCH_DIR/$FLAG_FILE"
	logger -t "$TAG" -p user.warning "Executing shutdown... Reason: '$REASON'"
        shutdown -h now
        exit 0
    fi
    sleep 5  # check every 5 seconds
done
