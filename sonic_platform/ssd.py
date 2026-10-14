#!/usr/bin/env python

########################################################################
# Juniper QFX5241-64OD
#
# Module contains an implementation of SONiC Platform Base API and
# provides the SSD information which are available in the platform.
#
########################################################################

import subprocess

class Ssd:
    def __init__(self, disk):
        self.disk = disk
        self.device = f"/dev/nvme{disk}"

    def get_model(self):
        """
        Return only the vendor prefix (e.g., 'PASCARI', 'EPM3750').
        """
        cmd = f"/usr/sbin/smartctl -a {self.device} 2>/dev/null"
        try:
            output = subprocess.check_output(cmd, shell=True, text=True)
            for line in output.splitlines():
                if line.startswith("Model Number:"):
                    model = line.split(":", 1)[1].strip()
                    return model.split()[0].split("-")[0]
            return "Not Available"
        except Exception:
            return "Not Available"
