/*
 * I2CS FPGA (jnx-i2cs-core) registers
 *
 * Copyright (C) 2014 Juniper Networks
 * Author: Georgi Vlaev <georgi.vlaev@konsulko.com>
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 as
 * published by the Free Software Foundation.
 */

#ifndef __JNX_I2CS_CORE_H__
#define __JNX_I2CS_CORE_H__

/* SIB I2CS registers */
#define I2CS_SCRATCH            0x00
#define I2CS_VERSION            0x01
#define I2CS_MASTER_STATUS      0x02
#define I2CS_MASTER_TIMEOUT     0x03
#define I2CS_MASTER_FORCE       0x04
#define I2CS_I2C0_STATUS        0x05
#define I2CS_I2C1_STATUS        0x06
#define I2CS_I2C_RESET          0x07
#define I2CS_DATECODE           0x0f
#define I2CS_INT_STATUS         0x10
#define I2CS_INT_ENABLE         0x11
#define I2CS_FRU_LED            0x12
#define I2CS_MISC_IO            0x13
#define I2CS_BUTTON_STATUS      0x14
#define I2CS_BUTTON_ENABLE      0x15
#define I2CS_GPIO_OE            0x16
#define I2CS_GPIO_OUT           0x17
#define I2CS_GPIO_IN            0x18
#define I2CS_SERIAL_CONFIG0     0x19
#define I2CS_SERIAL_CONFIG1     0x1a
#define I2CS_MII_CONFIG         0x1b
#define I2CS_MII_ADDR           0x1c
#define I2CS_MII_DATA0          0x1d
#define I2CS_MII_DATA1          0x1e
#define I2CS_MII_DATA2          0x1f
#define I2CS_PWR_CONTROL        0x20
#define I2CS_PWR_UP_STATUS      0x21
#define I2CS_PWR_DIS_STATUS     0x22
#define I2CS_PWR_DIS_CAUSE      0x23
#define I2CS_PWR_VFAIL_STATUS   0x24
#define I2CS_PWR_VFAIL_CAUSE    0x25
#define I2CS_PWR_TRIM_UP_A      0x26
#define I2CS_PWR_TRIM_UP_B      0x27
#define I2CS_PWR_TRIM_DN_A      0x28
#define I2CS_PWR_TRIM_DN_B      0x29
#define I2CS_PWR_VFAIL_STATUS_B 0x2a
#define I2CS_PWR_VFAIL_CAUSE_B  0x2b
#define I2CS_SCB                0x2c
#define I2CS_RESET_I2CS_REG     0x2d
#define I2CS_RESET_CONTROL      0x40
#define I2CS_SIB_ID_PORT_STATUS 0x41
#define I2CS_SIB_PCIE_GEN       0x42
#define I2CS_TF_LTC             0x43
#define I2CS_POWER_RST_HSWAP    0x44
#define I2CS_SIB_EN             0x45
#define I2CS_SIB_SPARE          0x46
#define I2CS_TF_PCIE_INT_STAT   0x47
#define I2CS_TF_PCIE_INT_EN     0x48
#define I2CS_SIB_MISC_0         0x49
#define I2CS_SIB_MISC_1         0x4a
#define I2CS_LINK_STATUS_0      0x4b
#define I2CS_LINK_STATUS_1      0x4c
#define I2CS_LINK_STATUS_2      0x4d
#define I2CS_LINK_STATUS_3      0x4e
#define I2CS_LINK_STATUS_4      0x4f
#define I2CS_LINK_STATUS_5      0x50
#define I2CS_LINK_STATUS_6      0x51
#define I2CS_LINK_STATUS_7      0x52
#define I2CS_LINK_STATUS_8      0x53
#define I2CS_LINK_STATUS_9      0x54
#define I2CS_LINK_STATUS_10     0x55
#define I2CS_LINK_STATUS_11     0x56
#define I2CS_LINK_STATUS_12     0x57
#define I2CS_LINK_STATUS_13     0x58
#define I2CS_LINK_STATUS_14     0x59
#define I2CS_LINK_STATUS_15     0x5a
#define I2CS_LINK_STATUS_16     0x5b
#define I2CS_LINK_STATUS_17     0x5c
#define I2CS_PWR_VFAIL_IGNORE_SNG       0x5d
#define I2CS_SPARE              0x5e
#define I2CS_SPARE_OE           0x5f
#define I2CS_FPC_STS_LED_CTRL   0x93
#define I2CS_MAX_REGISTER       I2CS_FPC_STS_LED_CTRL

struct mfd_cell;

struct jnx_i2cs_platform_data {
        int ncells;
        struct mfd_cell *cells;
};

#endif /*__JNX_I2CS_CORE_H__*/
