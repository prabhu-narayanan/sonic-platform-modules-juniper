#!/usr/bin/env bash
#
# extract_and_patch.sh - PAI-SDK build-time prep (invoked by the Makefile).
#
# Copyright (c) 2026 Hewlett Packard Enterprise Development LP
# All rights reserved.
#
# The PAI-SDK vendor tarballs are placed into common/phy/ by sonic-checkout.
# This script unpacks each tarball into its canonical component dir and applies
# the per-SDK Juniper patches, before compilation.
#
#   *.tgz                 provided by checkout (build-time only, .gitignore'd)
#   <component>/          extracted pristine vendor drop        (.gitignore'd)
#   patches/<component>/  Juniper patches applied on top        (tracked)
#
# Safe to re-run: files that were already extracted are kept (not overwritten),
# and patches that were already applied are skipped.
#
set -euo pipefail

log()  { echo "[pai-sdk] $*"; }
die()  { echo "[pai-sdk] ERROR: $*" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PHY_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PATCH_DIR="${PHY_DIR}/patches"

# Unpack one tarball into its canonical dir, then apply its per-SDK patches.
# $1 tarball basename   $2 canonical dest (rel PHY_DIR)   $3 patches/<subdir>
prepare() {
	local tgz="$1" dest_rel="$2" patchset="$3"
	local src="${PHY_DIR}/${tgz}"
	local dest="${PHY_DIR}/${dest_rel}"

	[ -f "${src}" ] || die "tarball not found in common/phy: ${tgz} (checkout should provide it)"

	# Unpack the tarball. --strip-components=1 removes the single top-level
	# folder inside the tarball so its contents land directly in <dest>.
	# Existing files are kept (not overwritten).
	mkdir -p "${dest}"
	log "extract ${tgz} -> ${dest_rel}/"
	tar -xaf "${src}" -C "${dest}" --strip-components=1 --keep-old-files 2>/dev/null || true

	# apply this SDK's patches; already-applied patches are skipped
	if [ -d "${PATCH_DIR}/${patchset}" ]; then
		for p in "${PATCH_DIR}/${patchset}"/*.patch; do
			[ -e "${p}" ] || continue
			log "patch  ${patchset}/$(basename "${p}") -> ${dest_rel}/"
			( cd "${dest}" && patch -p1 -N -s < "${p}" || true )
		done
	fi
}

prepare "PLP_EPDM_misc_4_6_0.tgz"    "epdm"               "epdm"
prepare "PLP_PAI_SW_misc_4_0.tgz"    "pai"                "pai"
prepare "PLP_AGERA3_SW_misc_1_0.tgz" "agera/AGR3_1_0"     "agera"
prepare "BARC_3_6.tgz"               "barchetta/BARC_3_6" "barchetta"
prepare "BFIN_2_22.tar"              "blackfin"           "blackfin"

log "done"
