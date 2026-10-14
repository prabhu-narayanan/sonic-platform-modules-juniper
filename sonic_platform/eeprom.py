#!/usr/bin/env python3
#
# eeprom.py — PDDF Eeprom wrapper with cache-file override
#
# Juniper PTX systems do not have standard I2C-accessible TLV EEPROM.
# Instead, platform init populates a binary TLV cache file at:
#     /var/run/platform_cache/onie_syseeprom.cache
#
# This wrapper overrides PddfEeprom.__init__() to read from the cache
# file instead of the PDDF I2C path. All TLV decoder methods (serial,
# model, base_mac, etc.) are inherited from the base class unchanged.
#
# Copyright (c) 2024, Juniper Networks, Inc.
# All rights reserved.
#

import os

try:
    from sonic_platform_pddf_base.pddf_eeprom import PddfEeprom
except ImportError as e:
    raise ImportError("%s - required module not found" % e)

PLATFORM_CACHE_DIR = "/var/run/platform_cache"
CACHE_FILE = os.path.join(PLATFORM_CACHE_DIR, "onie_syseeprom.cache")

# Standard TLV cache used by PddfEeprom base
PDDF_CACHE_ROOT = '/var/cache/sonic/decode-syseeprom'
PDDF_CACHE_FILE = 'syseeprom_cache'


class Eeprom(PddfEeprom):
    """Juniper PDDF Eeprom — reads from platform cache file.

    PTX systems populate /var/run/platform_cache/onie_syseeprom.cache
    during platform init. This class overrides the PDDF I2C path with
    the cache file so all TLV decoder methods work as-is.
    """

    def __init__(self, pddf_data=None, pddf_plugin_data=None):
        if not pddf_data or not pddf_plugin_data:
            raise ValueError('PDDF JSON data error')

        self.pddf_obj = pddf_data
        self.plugin_data = pddf_plugin_data

        # Override: use the platform cache file instead of PDDF I2C path
        if os.path.isfile(CACHE_FILE) and os.access(CACHE_FILE, os.R_OK):
            self.eeprom_path = CACHE_FILE
        else:
            # Fall back to PDDF I2C path (standard platforms)
            self.eeprom_path = self.pddf_obj.get_path("EEPROM1", "eeprom")

        if self.eeprom_path is None:
            raise RuntimeError("No EEPROM source: cache file missing and PDDF path unavailable")

        # Initialize TlvInfoDecoder base (skip PddfEeprom.__init__ to
        # avoid it calling get_path again)
        from sonic_eeprom import eeprom_tlvinfo
        eeprom_tlvinfo.TlvInfoDecoder.__init__(self, self.eeprom_path, 0, '', True)

        self.eeprom_tlv_dict = dict()

        # Set up decode-syseeprom cache directory
        if not os.path.exists(PDDF_CACHE_ROOT):
            try:
                os.makedirs(PDDF_CACHE_ROOT)
            except Exception as e:
                print("Error creating EEPROM cache directory: {}".format(e))

        try:
            self.set_cache_name(os.path.join(PDDF_CACHE_ROOT, PDDF_CACHE_FILE))
        except Exception:
            pass

        # Read and parse TLV data
        try:
            self.eeprom_data = self.read_eeprom()
        except Exception as e:
            self.eeprom_data = bytearray()
            import sys
            sys.stderr.write("EEPROM: Failed to read from {}: {}\n".format(
                self.eeprom_path, e))
            return

        eeprom = self.eeprom_data

        try:
            self.update_cache(eeprom)
        except Exception:
            pass

        if not self.is_valid_tlvinfo_header(eeprom):
            return

        total_length = (eeprom[9] << 8) | eeprom[10]
        tlv_index = self._TLV_INFO_HDR_LEN
        tlv_end = self._TLV_INFO_HDR_LEN + total_length

        while (tlv_index + 2) < len(eeprom) and tlv_index < tlv_end:
            if not self.is_valid_tlv(eeprom[tlv_index:]):
                break

            tlv_len = eeprom[tlv_index + 1]
            tlv = eeprom[tlv_index:tlv_index + 2 + tlv_len]
            code = "0x%02X" % tlv[0]

            if tlv[0] == self._TLV_CODE_VENDOR_EXT:
                if len(tlv) >= 6:
                    value = str((tlv[2] << 24) | (tlv[3] << 16) |
                                (tlv[4] << 8) | tlv[5])
                    value += tlv[6:6 + tlv_len].decode('ascii', errors='ignore')
                else:
                    name, value = self.decoder(None, tlv)
            else:
                name, value = self.decoder(None, tlv)

            self.eeprom_tlv_dict[code] = value
            if eeprom[tlv_index] == self._TLV_CODE_CRC_32:
                break

            tlv_index += tlv_len + 2
