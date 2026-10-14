#!/usr/bin/env python3

from sonic_py_common.logger import Logger

SYSLOG_IDENTIFIER = "qfx5241-post-pddf-init"


def log_info(msg):
    Logger(SYSLOG_IDENTIFIER).log_info(msg)


def main():
    # This hook runs on every boot after pddf_util.py install has loaded
    # drivers and created PDDF devices, but before pmon.service starts.
    log_info("Post-PDDF initialization completed")


if __name__ == '__main__':
    main()