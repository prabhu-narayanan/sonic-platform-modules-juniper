# Copyright (c) 2026 Hewlett Packard Enterprise Development LP
# All rights reserved.
#
# Top-level Makefile to build libbrcm_pai.so from the PHY SDKs extracted into
# common/phy/ by scripts/extract_and_patch.sh. One shared object carries all
# PHY families (EPDM + PAI + Agera + Barchetta) and is used by both gbsyncd
# dockers.
#
# Usage:
#   make          # build output/libbrcm_pai.so
#   make clean

PHY_DIR    := $(CURDIR)
EPDM_DIR   := $(PHY_DIR)/epdm
PAI_DIR    := $(PHY_DIR)/pai
AGR3_DIR   := $(PHY_DIR)/agera/AGR3_1_0
BARC_DIR   := $(PHY_DIR)/barchetta/BARC_3_6
BFIN_DIR   := $(PHY_DIR)/blackfin
OUTPUT_DIR := $(PHY_DIR)/output

# ---- Derived compile flags -------------------------------------------------
# All build configuration for EPDM and PAI lives here; patches/ carries source
# changes only. These are passed as CFLAGS= on the sub-make command line, which
# replaces (not extends) the vendor Makefile's CFLAGS, so each list is complete.
# Keep this base list PHY-agnostic: anything specific to a PHY family belongs in
# that family's conditional block below, so adding a family cannot change how
# the others are compiled.
EPDM_CFLAGS := -g -Wall -Werror -Wno-uninitialized -fPIC \
	-DSERDES_API_FLOATING_POINT

PAI_CFLAGS := -g -Wall -Werror -Wno-uninitialized -fPIC -rdynamic \
	-DBRCM_PAI_PROP -DPAI_QUERY_ATTR_CAPABILITY_ENABLE \
	-DBASET_HSIP_MACSEC_SUPPORT -DOPTIMIZED_SYNC \
	-DMULTIPHY_SUPPORT -lpthread \
	-DSERDES_API_FLOATING_POINT

AGR3_CFLAGS := -fPIC -g -Wall -Werror -Wno-uninitialized
BARC_CFLAGS := -fPIC -g -Wall -Werror -Wno-uninitialized -Wno-address
BFIN_CFLAGS := -fPIC -g -Wall -Werror -Wno-uninitialized -Wno-address

# ---- Components: one library carries every PHY family present --------------
# Each SDK is optional: only the trees actually extracted under common/phy are
# compiled in, so a board that ships a subset still links.
ifneq ($(wildcard $(AGR3_DIR)/Makefile),)
EPDM_CFLAGS += -DPLP_AGERA3_SUPPORT
PAI_CFLAGS  += -DPLP_AGERA3_SUPPORT
PHYMOD_LIBS += $(AGR3_DIR)/build/libphymodepil.a
endif

ifneq ($(wildcard $(BARC_DIR)/Makefile),)
EPDM_CFLAGS += -DPLP_BARCHETTA_SUPPORT
PAI_CFLAGS  += -DPLP_BARCHETTA_SUPPORT
PHYMOD_LIBS += $(BARC_DIR)/build/libphymodepil.a
endif

ifneq ($(wildcard $(BFIN_DIR)/Makefile),)
EPDM_CFLAGS += -DPLP_BLACKFIN_SUPPORT -DBCM_PLP_BASE_T_PHY
# EXT_MDIO_APIS selects PAI's internal MDIO client, which the patch maps to the
# CL45 entry points required by BCM84894. SWITCH_HARDWARE_INFO_STRING_FORMAT
# takes SAI_SWITCH_ATTR_SWITCH_HARDWARE_INFO as a string rather than a packed
# 4-byte value. Both are scoped here: they change how attributes shared with
# Agera3/Barchetta are interpreted, so they must not apply to those builds.
# pai/Makefile pairs EXT_MDIO_APIS with -Wno-format-truncation via CFLAGS+=,
# which a command-line CFLAGS= cannot append to, so it is repeated here.
PAI_CFLAGS  += -DPLP_BLACKFIN_SUPPORT \
	-DEXT_MDIO_APIS -DSWITCH_HARDWARE_INFO_STRING_FORMAT \
	-Wno-format-truncation
PHYMOD_LIBS += $(BFIN_DIR)/build/libphymodepil.a
endif

# Vendor tarballs are placed in common/phy/ by sonic-checkout. Unpack + patch
# them once (per-SDK patches under patches/<component>/) before compiling.
PREPARED := $(PHY_DIR)/.prepared

.PHONY: all build clean

# Two passes: the SDK presence tests below use $(wildcard ...), which make
# evaluates while parsing -- before .prepared has extracted anything. Extract
# first, then re-enter so the extracted trees are visible.
all: $(PREPARED)
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) build

build: $(OUTPUT_DIR)/libbrcm_pai.so

$(PREPARED): $(PHY_DIR)/scripts/extract_and_patch.sh
	$(PHY_DIR)/scripts/extract_and_patch.sh
	touch $@

$(OUTPUT_DIR):
	mkdir -p $(OUTPUT_DIR)

# Build EPDM static library (PHY-agnostic core)
$(EPDM_DIR)/libepdm.a: $(PREPARED)
	$(MAKE) -C $(EPDM_DIR) PWD="$(EPDM_DIR)" clean
	$(MAKE) -C $(EPDM_DIR) PWD="$(EPDM_DIR)" "CFLAGS=$(EPDM_CFLAGS)"

# Build Agera phymod static library.
# AGR3_1_0/make/config.mk does `override CFLAGS = $(PHYMOD_CFLAGS) ...`, so the
# flags (incl. -fPIC, required to link into a shared object) must be passed via
# PHYMOD_CFLAGS, not CFLAGS.
$(AGR3_DIR)/build/libphymodepil.a: $(PREPARED)
	$(MAKE) -C $(AGR3_DIR) EPDM_HOME="$(EPDM_DIR)" clean
	$(MAKE) -C $(AGR3_DIR) EPDM_HOME="$(EPDM_DIR)" "PHYMOD_CFLAGS=$(AGR3_CFLAGS)"

# Build Barchetta phymod static library
$(BARC_DIR)/build/libphymodepil.a: $(PREPARED)
	$(MAKE) -C $(BARC_DIR) EPDM_HOME="$(EPDM_DIR)" clean
	$(MAKE) -C $(BARC_DIR) EPDM_HOME="$(EPDM_DIR)" "PHYMOD_CFLAGS=$(BARC_CFLAGS)"

# Build Blackfin (BCM84894) phymod static library. Same phymod convention as
# Agera/Barchetta: make/config.mk overrides CFLAGS, so flags go via PHYMOD_CFLAGS.
$(BFIN_DIR)/build/libphymodepil.a: $(PREPARED)
	$(MAKE) -C $(BFIN_DIR) EPDM_HOME="$(EPDM_DIR)" clean
	$(MAKE) -C $(BFIN_DIR) EPDM_HOME="$(EPDM_DIR)" "PHYMOD_CFLAGS=$(BFIN_CFLAGS)"

# Build PAI static library (src/ only, no reference apps)
$(PAI_DIR)/build/libpai.a: $(PREPARED)
	$(MAKE) -C $(PAI_DIR) PWD="$(PAI_DIR)" clean
	$(MAKE) -C $(PAI_DIR) PWD="$(PAI_DIR)" "CFLAGS=$(PAI_CFLAGS)"

# Link all components into a single shared object. Archive order and the absence
# of -lm/-lpthread here match the vendor reference-app recipe: phymod driver
# first, then EPDM, then PAI.
$(OUTPUT_DIR)/libbrcm_pai.so: $(EPDM_DIR)/libepdm.a $(PHYMOD_LIBS) $(PAI_DIR)/build/libpai.a | $(OUTPUT_DIR)
	gcc -shared -o $@ \
	  -Wl,--whole-archive \
		$(PHYMOD_LIBS) \
		$(EPDM_DIR)/libepdm.a \
		$(PAI_DIR)/build/libpai.a \
	  -Wl,--no-whole-archive

# clean removes the extracted trees, build output, and the prepared stamp, but
# keeps the *.tgz (provided by checkout) so a rebuild re-extracts pristine.
clean:
	rm -rf $(EPDM_DIR) $(PAI_DIR) $(PHY_DIR)/agera $(PHY_DIR)/barchetta $(PHY_DIR)/blackfin $(OUTPUT_DIR) $(PREPARED)
