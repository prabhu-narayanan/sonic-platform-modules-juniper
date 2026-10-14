#!/bin/bash
#
# PDDF post-driver-install hook.
#
# pddf_util.py driver_install() runs /usr/local/bin/pddf_post_driver_install.sh
# (if present) right after std_kos/pddf_kos/custom_kos have been modprobed and
# before device_install() -> create_pddf_devices() walks pddf-device.json.
#
# The real work (udevadm settle, to close the race between driver probing
# and PDDF's dynamic pca9548 mux-channel creation) has no platform-specific
# logic, so it runs unconditionally for every platform via the common
# pddf_post_driver_install.py script (installed by sonic-platform-juniper-common).

set -u

exec /usr/bin/python3 /usr/local/bin/pddf_post_driver_install.py
