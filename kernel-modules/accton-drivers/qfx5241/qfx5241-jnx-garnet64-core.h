/* SPDX-License-Identifier: GPL-2.0
 *
 * Juniper GARNET-64 MFD resources
 *
 * This file is used by jnx-garnet-core.c
 *
 * Copyright (c) 2024, Juniper Networks
 * Author: Arun kumar Alapati (arunkumara@juniper.net)
 *
 * This program is free software; you can redistribute it and/or
 * modify it under the terms of the GNU General Public License
 * version 2 as published by the Free Software Foundation.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 */
#ifndef __JNX_GARNET64_CORE__
#define __JNX_GARNET64_CORE__

#define GARNET64_PORT_COUNT     66
#define GARNET64_I2C_STRL_LEN   11

#define GARNET64_FPGA_VER_SPI_LOCK_MAJOR        0x5C
#define GARNET64_FPGA_VER_SPI_LOCK_MINOR        0x01

struct system_led_config {
    const char *name;
    int led_type;
    unsigned int rgb_reg_base_offset;
    unsigned int blink_reg_offset;
    unsigned int blink_reg_bit_offset;
};

struct port_led_config {
    const char *label;
    int led_type; // 3 - OSFP, 4 - SFP
    unsigned int rgb_reg_base_offset;
    unsigned int bit_offset;
};

struct garnet_system_led_platform_data {
    int num_leds;
    struct system_led_config *leds;
};

struct garnet_port_led_platform_data {
    int num_leds;
    struct port_led_config *leds;
};

static struct system_led_config platform_leds[] = {
    {"beacon", 0, 0x2, 0xc, 0x16},
    {"system", 1, 0x8, 0xc, 0x1d},
    {"alarm",  2, 0xb, 0x10, 0x1}
};

static struct port_led_config cpld1_port_leds[] = {
    {"fpc0-port0", 3, 0x0, 0x0},
    {"fpc0-port1", 3, 0x0, 0x1},
    {"fpc0-port2", 3, 0x6, 0x0},
    {"fpc0-port3", 3, 0x6, 0x1},
    {"fpc0-port4", 3, 0x0, 0x2},
    {"fpc0-port5", 3, 0x0, 0x3},
    {"fpc0-port6", 3, 0x6, 0x2},
    {"fpc0-port7", 3, 0x6, 0x3},
    {"fpc0-port8", 3, 0x0, 0x4},
    {"fpc0-port9", 3, 0x0, 0x5},
    {"fpc0-port10", 3, 0x6, 0x4},
    {"fpc0-port11", 3, 0x6, 0x5},
    {"fpc0-port12", 3, 0x0, 0x6},
    {"fpc0-port13", 3, 0x0, 0x7},
    {"fpc0-port14", 3, 0x6, 0x6},
    {"fpc0-port15", 3, 0x6, 0x7},
    {"fpc0-port16", 3, 0x3, 0x0},
    {"fpc0-port17", 3, 0x3, 0x1},
    {"fpc0-port18", 3, 0x9, 0x0},
    {"fpc0-port19", 3, 0x9, 0x1},
    {"fpc0-port20", 3, 0x3, 0x2},
    {"fpc0-port21", 3, 0x3, 0x3},
    {"fpc0-port22", 3, 0x9, 0x2},
    {"fpc0-port23", 3, 0x9, 0x3},
    {"fpc0-port24", 3, 0x3, 0x4},
    {"fpc0-port25", 3, 0x3, 0x5},
    {"fpc0-port26", 3, 0x9, 0x4},
    {"fpc0-port27", 3, 0x9, 0x5},
    {"fpc0-port28", 3, 0x3, 0x6},
    {"fpc0-port29", 3, 0x3, 0x7},
    {"fpc0-port30", 3, 0x9, 0x6},
    {"fpc0-port31", 3, 0x9, 0x7},
};

static struct port_led_config cpld2_port_leds[] = {
    {"fpc0-port32", 3, 0x0, 0x0},
    {"fpc0-port33", 3, 0x0, 0x1},
    {"fpc0-port34", 3, 0x6, 0x0},
    {"fpc0-port35", 3, 0x6, 0x1},
    {"fpc0-port36", 3, 0x0, 0x2},
    {"fpc0-port37", 3, 0x0, 0x3},
    {"fpc0-port38", 3, 0x6, 0x2},
    {"fpc0-port39", 3, 0x6, 0x3},
    {"fpc0-port40", 3, 0x0, 0x4},
    {"fpc0-port41", 3, 0x0, 0x5},
    {"fpc0-port42", 3, 0x6, 0x4},
    {"fpc0-port43", 3, 0x6, 0x5},
    {"fpc0-port44", 3, 0x0, 0x6},
    {"fpc0-port45", 3, 0x0, 0x7},
    {"fpc0-port46", 3, 0x6, 0x6},
    {"fpc0-port47", 3, 0x6, 0x7},
    {"fpc0-port48", 3, 0x3, 0x0},
    {"fpc0-port49", 3, 0x3, 0x1},
    {"fpc0-port50", 3, 0x9, 0x0},
    {"fpc0-port51", 3, 0x9, 0x1},
    {"fpc0-port52", 3, 0x3, 0x2},
    {"fpc0-port53", 3, 0x3, 0x3},
    {"fpc0-port54", 3, 0x9, 0x2},
    {"fpc0-port55", 3, 0x9, 0x3},
    {"fpc0-port56", 3, 0x3, 0x4},
    {"fpc0-port57", 3, 0x3, 0x5},
    {"fpc0-port58", 3, 0x9, 0x4},
    {"fpc0-port59", 3, 0x9, 0x5},
    {"fpc0-port60", 3, 0x3, 0x6},
    {"fpc0-port61", 3, 0x3, 0x7},
    {"fpc0-port62", 3, 0x9, 0x6},
    {"fpc0-port63", 3, 0x9, 0x7},};

static struct port_led_config sfp_port_leds[] = {
    {"fpc0-port64", 4, 0x00, 0x00},
    {"fpc0-port65", 4, 0x00, 0x01},
};

static struct garnet_system_led_platform_data garnet64_system_led_data = {
    .num_leds = ARRAY_SIZE(platform_leds),
    .leds = platform_leds,
};

static struct garnet_port_led_platform_data garnet64_cpld1_port_led_data = {
    .num_leds = ARRAY_SIZE(cpld1_port_leds),
    .leds = cpld1_port_leds,
};

static struct garnet_port_led_platform_data garnet64_cpld2_port_led_data = {
    .num_leds = ARRAY_SIZE(cpld2_port_leds),
    .leds = cpld2_port_leds,
};

static struct garnet_port_led_platform_data garnet64_sfp_port_led_data = {
    .num_leds = ARRAY_SIZE(sfp_port_leds),
    .leds = sfp_port_leds,
};

static struct resource garnet64_resource_gpioslave0_presence[] = {
        {
                .name = "actn-gpioslave0-presence-gmc",
                .start = GARNET64_GPIO_CPLD1_PRESENCE_START,
                .end   = GARNET64_GPIO_CPLD1_PRESENCE_END,
                .flags = IORESOURCE_MEM,
        }
};

static struct resource garnet64_resource_gpioslave1_presence[] = {
        {
                .name = "actn-gpioslave1-presence-gmc",
                .start = GARNET64_GPIO_CPLD2_PRESENCE_START,
                .end   = GARNET64_GPIO_CPLD2_PRESENCE_END,
                .flags = IORESOURCE_MEM,
        }
};

static struct resource garnet64_resource_gpioslave0_lpmod[] = {
        {
                .name = "actn-gpioslave0-lpmod-gmc",
                .start = GARNET64_GPIO_CPLD1_LPMOD_START,
                .end   = GARNET64_GPIO_CPLD1_LPMOD_END,
                .flags = IORESOURCE_MEM,
        }
};

static struct resource garnet64_resource_gpioslave1_lpmod[] = {
        {
                .name = "actn-gpioslave1-lpmod-gmc",
                .start = GARNET64_GPIO_CPLD2_LPMOD_START,
                .end   = GARNET64_GPIO_CPLD2_LPMOD_END,
                .flags = IORESOURCE_MEM,
        }
};

static struct resource garnet64_resource_gpioslave0_reset[] = {
        {
                .name = "actn-gpioslave0-reset-gmc",
                .start = GARNET64_GPIO_CPLD1_RESET_START,
                .end   = GARNET64_GPIO_CPLD1_RESET_END,
                .flags = IORESOURCE_MEM,
        }
};

static struct resource garnet64_resource_gpioslave1_reset[] = {
        {
                .name = "actn-gpioslave1-reset-gmc",
                .start = GARNET64_GPIO_CPLD2_RESET_START,
                .end   = GARNET64_GPIO_CPLD2_RESET_END,
                .flags = IORESOURCE_MEM,
        }
};

static struct resource garnet64_resource_gpioslave0_pwr_good[] = {
        {
                .name = "actn-gpioslave0-pwr-good",
                .start = GARNET64_GPIO_CPLD1_PWR_GOOD_START,
                .end   = GARNET64_GPIO_CPLD1_PWR_GOOD_END,
                .flags = IORESOURCE_MEM,
        }
};

static struct resource garnet64_resource_gpioslave1_pwr_good[] = {
        {
                .name = "actn-gpioslave1-pwr-good",
                .start = GARNET64_GPIO_CPLD2_PWR_GOOD_START,
                .end   = GARNET64_GPIO_CPLD2_PWR_GOOD_END,
                .flags = IORESOURCE_MEM,
        }
};

static struct resource garnet64_resource_gpioslave1_sfp_pres[] = {
        {
                .name = "actn-gpioslave1-sfp-pres-gmc",
                .start = GARNET64_GPIO_CPLD2_SFP28_PRESENCE_START,
                .end   = GARNET64_GPIO_CPLD2_SFP28_PRESENCE_END,
                .flags = IORESOURCE_MEM,
        }
};

static struct resource garnet64_resource_gpioslave1_sfp_tx_dis[] = {
        {
                .name = "actn-gpioslave1-sfp-tx_dis-gmc",
                .start = GARNET64_GPIO_CPLD2_SFP28_TX_DIS_START,
                .end   = GARNET64_GPIO_CPLD2_SFP28_TX_DIS_END,
                .flags = IORESOURCE_MEM,
        }
};

static struct resource garnet64_resource_gpioslave1_sfp_tx_fault[] = {
        {
                .name = "actn-gpioslave1-sfp-tx_fault-gmc",
                .start = GARNET64_GPIO_CPLD2_SFP28_TX_FAULT_START,
                .end   = GARNET64_GPIO_CPLD2_SFP28_TX_FAULT_END,
                .flags = IORESOURCE_MEM,
        }
};

static struct resource garnet64_resource_gpioslave1_sfp_rx_los[] = {
        {
                .name = "actn-gpioslave1-sfp-rx_los-gmc",
                .start = GARNET64_GPIO_CPLD2_SFP28_RX_LOS_START,
                .end   = GARNET64_GPIO_CPLD2_SFP28_RX_LOS_END,
                .flags = IORESOURCE_MEM,
        }
};

static struct resource garnet64_resource_fpga_system_leds[] = {
        {
                .name = "actn-resource-fpga-system-leds",
                .start = GARNET64_GPIO_FPGA_SYSTEM_LED_START,
                .end   = GARNET64_GPIO_FPGA_SYSTEM_LED_END,
                .flags = IORESOURCE_MEM,
        }
};

static struct resource garnet_psu[] = {
        /* PSU Presence Block */
        {
                .name  = "garnet-psu",
                .start = GARNET64_PSU_START,
                .end   = GARNET64_PSU_END,
                .flags = IORESOURCE_MEM,
        }
};

static struct resource garnet64_resource_cpld1_port_leds[] = {
        {
                .name = "actn-resource-cpld1-port-leds",
                .start = GARNET64_GPIO_CPLD1_PORT_LED_START,
                .end   = GARNET64_GPIO_CPLD1_PORT_LED_END,
                .flags = IORESOURCE_MEM,
        }
};

static struct resource garnet64_resource_cpld2_port_leds[] = {
        {
                .name = "actn-resource-cpld2-port-leds",
                .start = GARNET64_GPIO_CPLD2_PORT_LED_START,
                .end   = GARNET64_GPIO_CPLD2_PORT_LED_END,
                .flags = IORESOURCE_MEM,
        }
};

static struct resource garnet64_resource_cpld2_sfp_port_leds[] = {
        {
                .name = "actn-resource-cpld2-sfp-port-leds",
                .start = GARNET64_GPIO_CPLD2_SFP_PORT_LED_START,
                .end   = GARNET64_GPIO_CPLD2_SFP_PORT_LED_END,
                .flags = IORESOURCE_MEM,
        }
};

static struct mfd_cell garnet64_cpld1_mfd_devs[] = {
        {
                .name = "cpld1-port-leds",
                .platform_data = (void *)(&garnet64_cpld1_port_led_data),
                .pdata_size = sizeof(garnet64_cpld1_port_led_data),
                .num_resources = ARRAY_SIZE(garnet64_resource_cpld1_port_leds),
                .resources = &garnet64_resource_cpld1_port_leds[0],
                .id = 0,
        },
        {
                .name = "garnet-gpio-gmc",
                .num_resources = ARRAY_SIZE(garnet64_resource_gpioslave0_presence),
                .resources = &garnet64_resource_gpioslave0_presence[0],
                .of_compatible = "jnx,actn-gpioslave0-presence-gmc",
                .id = 1,
        },
        {
                .name = "garnet-gpio-gmc",
                .num_resources = ARRAY_SIZE(garnet64_resource_gpioslave0_lpmod),
                .resources = &garnet64_resource_gpioslave0_lpmod[0],
                .of_compatible = "jnx,actn-gpioslave0-lpmod-gmc",
                .id = 2,
        },
        {
                .name = "garnet-gpio-gmc",
                .num_resources = ARRAY_SIZE(garnet64_resource_gpioslave0_reset),
                .resources = &garnet64_resource_gpioslave0_reset[0],
                .of_compatible = "jnx,actn-gpioslave0-reset-gmc",
                .id = 3,
        },
        {
                .name = "garnet-gpio-gmc",
                .num_resources = ARRAY_SIZE(garnet64_resource_gpioslave0_pwr_good),
                .resources = &garnet64_resource_gpioslave0_pwr_good[0],
                .of_compatible = "jnx,actn-gpioslave0-pwr-good",
                .id = 4,
        },
};

static struct mfd_cell garnet64_cpld2_mfd_devs[] = {
        {
                .name = "cpld2-port-leds",
                .platform_data = (void *)(&garnet64_cpld2_port_led_data),
                .pdata_size = sizeof(garnet64_cpld2_port_led_data),
                .num_resources = ARRAY_SIZE(garnet64_resource_cpld2_port_leds),
                .resources = &garnet64_resource_cpld2_port_leds[0],
                .id = 0,
        },
        {
                .name = "sfp-port-leds",
                .platform_data = (void *)(&garnet64_sfp_port_led_data),
                .pdata_size = sizeof(garnet64_sfp_port_led_data),
                .num_resources = ARRAY_SIZE(garnet64_resource_cpld2_sfp_port_leds),
                .resources = &garnet64_resource_cpld2_sfp_port_leds[0],
                .id = 0,
        },
        {
                .name = "garnet-gpio-gmc",
                .num_resources = ARRAY_SIZE(garnet64_resource_gpioslave1_presence),
                .resources = &garnet64_resource_gpioslave1_presence[0],
                .of_compatible = "jnx,actn-gpioslave1-presence-gmc",
                .id = 7,
        },
        {
                .name = "garnet-gpio-gmc",
                .num_resources = ARRAY_SIZE(garnet64_resource_gpioslave1_reset),
                .resources = &garnet64_resource_gpioslave1_reset[0],
                .of_compatible = "jnx,actn-gpioslave1-reset-gmc",
                .id = 8,
        },
        {
                .name = "garnet-gpio-gmc",
                .num_resources = ARRAY_SIZE(garnet64_resource_gpioslave1_pwr_good),
                .resources = &garnet64_resource_gpioslave1_pwr_good[0],
                .of_compatible = "jnx,actn-gpioslave1-pwr-good",
                .id = 9,
        },
        {
                .name = "garnet-gpio-gmc",
                .num_resources = ARRAY_SIZE(garnet64_resource_gpioslave1_lpmod),
                .resources = &garnet64_resource_gpioslave1_lpmod[0],
                .of_compatible = "jnx,actn-gpioslave1-lpmod-gmc",
                .id = 10,
        },
        {
                .name = "garnet-gpio-gmc",
                .num_resources = ARRAY_SIZE(garnet64_resource_gpioslave1_sfp_pres),
                .resources = &garnet64_resource_gpioslave1_sfp_pres[0],
                .of_compatible = "jnx,actn-gpioslave1-sfp-pres-gmc",
                .id = 11,
        },
        {
                .name = "garnet-gpio-gmc",
                .num_resources =
                        ARRAY_SIZE(garnet64_resource_gpioslave1_sfp_tx_dis),
                .resources = &garnet64_resource_gpioslave1_sfp_tx_dis[0],
                .of_compatible = "jnx,actn-gpioslave1-sfp-tx_dis-gmc",
                .id = 12,
        },
        {
                .name = "garnet-gpio-gmc",
                .num_resources =
                        ARRAY_SIZE(garnet64_resource_gpioslave1_sfp_tx_fault),
                .resources = &garnet64_resource_gpioslave1_sfp_tx_fault[0],
                .of_compatible = "jnx,actn-gpioslave1-sfp-tx_fault-gmc",
                .id = 13,
        },
        {
                .name = "garnet-gpio-gmc",
                .num_resources =
                        ARRAY_SIZE(garnet64_resource_gpioslave1_sfp_rx_los),
                .resources = &garnet64_resource_gpioslave1_sfp_rx_los[0],
                .of_compatible = "jnx,actn-gpioslave1-sfp-rx_los-gmc",
                .id = 14,
        },
};

static struct mfd_cell garnet64_fpga_mfd_devs[] = {
        {
                .name = "fpga-system-leds",
                .platform_data = (void *)(&garnet64_system_led_data),
                .pdata_size = sizeof(garnet64_system_led_data),
                .num_resources = ARRAY_SIZE(garnet64_resource_fpga_system_leds),
                .resources = &garnet64_resource_fpga_system_leds[0],
                .id = 0,
        },
        {
                .name = "garnet-psu",
                .num_resources = ARRAY_SIZE(garnet_psu),
                .resources = &garnet_psu[0],
                .of_compatible = "jnx,garnet-psu",
                .id = 0,
        },

};

#ifdef QFX_SONIC
static struct mfd_cell garnet64_cpld1_mfd_i2c_devs[32];
static struct mfd_cell garnet64_cpld2_mfd_i2c_devs[34];
static struct resource garnet64_resource_i2c[GARNET64_PORT_COUNT];
static char garnet64_i2c_dev_str[GARNET64_PORT_COUNT][GARNET64_I2C_STRL_LEN];
#endif

#endif
