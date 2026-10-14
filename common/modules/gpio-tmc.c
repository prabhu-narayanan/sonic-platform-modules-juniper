/*
 * Juniper TMC GPIO driver
 *
 * drivers/gpio/gpio-tmc.c
 *
 * This driver is being adpoted from supercon FPGA driver.
 *
 * Copyright (C) 2018 Juniper Networks
 * Author: Ashish Bhensdadia <bashish@juniper.net>
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; version 2 of the License.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 */
#include <linux/device.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/gpio.h>
#include <linux/errno.h>
#include <linux/of_device.h>
#include <linux/of_platform.h>
#include <linux/of_gpio.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/sched.h>
#include "jnx-tmc.h"

#define TMC_GPIO_MAX_BITS_PER_REG	16
#define TMC_GPIO_SFP_MAX_BITS_PER_REG	2
#define TMC_GPIO_PTPCFG_MAX_BITS_PER_REG	16
#define XMC_GPIO_MAX_BITS_PER_REG   32
#define TXMC_GPIO_SFP_MAX_BITS_PER_REG 2
#define TXMC_GPIO_DEV_MAX_BITS_PER_REG  6

#define XMC_GPIO_FIND_GROUP(gpio)   \
	((gpio) / XMC_GPIO_MAX_BITS_PER_REG)
#define XMC_GPIO_FIND_GPIO(gpio)    \
	((gpio) % XMC_GPIO_MAX_BITS_PER_REG)

#define TXMC_GPIO_FIND_GROUP(gpio)   \
	((gpio) / XMC_GPIO_MAX_BITS_PER_REG)
#define TXMC_GPIO_FIND_GPIO(gpio)    \
	((gpio) % XMC_GPIO_MAX_BITS_PER_REG)

#define TXMC_GPIO_SFP_FIND_GROUP(gpio)   \
	((gpio) / TXMC_GPIO_SFP_MAX_BITS_PER_REG)
#define TXMC_GPIO_SFP_FIND_GPIO(gpio)    \
	((gpio) % TXMC_GPIO_SFP_MAX_BITS_PER_REG)

#define TXMC_GPIO_DEV_FIND_GROUP(gpio)   \
	((gpio) / TXMC_GPIO_DEV_MAX_BITS_PER_REG)
#define TXMC_GPIO_DEV_FIND_GPIO(gpio)    \
	((gpio) % TXMC_GPIO_DEV_MAX_BITS_PER_REG)

#define TMC_GPIO_FIND_GROUP(gpio)	\
			((gpio) / TMC_GPIO_MAX_BITS_PER_REG)
#define TMC_GPIO_FIND_GPIO(gpio)	\
			((gpio) % TMC_GPIO_MAX_BITS_PER_REG)

#define TMC_GPIO_SFP_FIND_GROUP(gpio)	\
			((gpio) / TMC_GPIO_SFP_MAX_BITS_PER_REG)
#define TMC_GPIO_SFP_FIND_GPIO(gpio)	\
			((gpio) % TMC_GPIO_SFP_MAX_BITS_PER_REG)

#define TMC_GPIO_PTPCFG_FIND_GPIO(gpio)	\
			((gpio) % TMC_GPIO_PTPCFG_MAX_BITS_PER_REG)

#define TMC_GPIO_PTPDATA_SET_MASK_PER_REG      0xFF

#define TMC_GPIO_MAX_NGPIO_PER_GROUP		414

#define TMC_PFE_QSFP_RESET_OFFSET       	0x4
#define TMC_PFE_QSFP_PRESENT_OFFSET		0x8
#define TMC_PFE_QSFP_PHY_RESET_OFFSET		0x10
#define TMC_PFE_QSFP_LPMOD_OFFSET		0x78
#define TMC_PFE_QSFP_LED_CTRL_OFFSET		0x20

#define TMC_PFE_LANES_GREEN_LED_VALUE         0x3
#define TMC_PFE_LANES_BEACON_LED_VALUE         0x2
#define TMC_PFE_LANES_FAULT_LED_VALUE         0x1
#define TMC_PFE_LANES_AMBER_LED_VALUE          0x5
#define TMC_PFE_LANES_SFP_AMBER_LED_VALUE      0x4

#define TMC_PFE_SFPSB0_TX_DISABLE_OFFSET   	0x0
#define TMC_PFE_SFPSB0_LED_CTRL_OFFSET     	0xC
#define TMC_PFE_SFPSB0_LED_ACTIVITY_OFFSET 	0x14
#define TMC_PFE_SFPSB0_PRESENT_OFFSET      	0x18
#define TMC_PFE_SFPSB0_LOSS_OFFSET         	0x1C
#define TMC_PFE_SFPSB0_TX_FAULT_OFFSET     	0x20

#define TMC_PFE_SFPSB1_TX_DISABLE_OFFSET   	0x0
#define TMC_PFE_SFPSB1_LED_CTRL_OFFSET     	0x8
#define TMC_PFE_SFPSB1_LED_ACTIVITY_OFFSET 	0x10
#define TMC_PFE_SFPSB1_PRESENT_OFFSET      	0x14
#define TMC_PFE_SFPSB1_LOSS_OFFSET         	0x18
#define TMC_PFE_SFPSB1_TX_FAULT_OFFSET     	0x1C

/*
 * Index 4 to 20 is used for QSFP starting with
 * QSFP_LED_LANE0_GREEN. To keep multibit set/get common
 * starting SFP_LED_LANE0_GREEN with 20 which will avoid
 * conflict with QSFP enums.
 */
#define SFP_LED_OP_START_INDEX   	20

/*
 * Used for off-setting SFP led op index
 */
#define SFP_LED_OP_OFFSET   	0xF

/*
 * SFP slave blocks
 */
#define SFP_SLAVE0_BLOCK   	0x1
#define SFP_SLAVE1_BLOCK   	0x2

/* XMC register offsets */
#define XMC_PFE_SFP_TX_DISABLE_OFFSET   0x4
#define XMC_PFE_SFP_PRESENT_OFFSET      0x8
#define XMC_PFE_SFP_TX_FAULT_OFFSET     0xC
#define XMC_PFE_SFP_LOSS_OFFSET         0x10
#define XMC_PFE_LED_ACTIVITY_OFFSET     0x80
#define XMC_PFE_SW_LED_ACTIVITY_OFFSET  0x84
#define XMC_PFE_QSFP_LPMOD_OFFSET       0x88
#define XMC_PFE_PORT_LED_CTRL_OFFSET    0x20
#define XMC_PFE_SFP_MAINBOARD_PRESENT   0x70
#define XMC_PFE_SFP_MAINBOARD_TXDISABLE 0x40

#define XMC_PFE_MFGTEST_LED_VALUE       0x7
#define XMC_PFE_GREEN_LED_VALUE         0x3
#define XMC_PFE_BEACON_LED_VALUE        0x2
#define XMC_PFE_FAULT_LED_VALUE         0x1

#define XMC_MAX_PORT_PER_REG		4
#define XMC_MAX_BITS_PER_LED		8


/* TXMC gpioslave0/slave1 offsets */
#define TXMC_PFE_QSFP_RESET_OFFSET       0x4
#define TXMC_PFE_QSFP_PRESENT_OFFSET     0x8
#define TXMC_PFE_PORT_LED_CTRL_OFFSET    0x20
/* TXMC gpioslave1-sfp-txmc offsets */
#define TXMC_PFE_SFP_TX_DISABLE_OFFSET   0x0
#define TXMC_PFE_SFP_LED_CTRL_OFFSET     0x4
#define TXMC_PFE_SFP_PRESENT_OFFSET      0x10
#define TXMC_PFE_SFP_LOSS_OFFSET         0x14
#define TXMC_PFE_SFP_TX_FAULT_OFFSET     0x18
/* TXMC gpioslave2 offsets */
#define TXMC_PFE_QSFP_PWR_GOOD_STATUS0   0x10
#define TXMC_PFE_QSFP_PWR_GOOD_STATUS1   0x14
/* TXMC extdevice offset */
#define TXMC_EXT_DEVICE_RESET_OFFSET     0x0

#define TXMC_PFE_GREEN_LED_VALUE         0x1
#define TXMC_PFE_FAULT_LED_VALUE         0x2
#define TXMC_PFE_AMBER_LED_VALUE         0x3
#define TXMC_PFE_GREEN_BEACON_LED_VALUE  0x4
#define TXMC_PFE_FAULT_BEACON_LED_VALUE  0x5
#define TXMC_PFE_AMBER_BEACON_LED_VALUE  0x6
#define TXMC_PFE_MFGTEST_LED_VALUE       0x7

#define TXMC_MAX_PORT_PER_REG		4
#define TXMC_MAX_BITS_PER_LED		8

/*
 * Used for off-setting TXMC SFP led op index
 */
#define TXMC_SFP_LED_OP_OFFSET		0x7

/*
 * each group represent the 16 gpios.
 * QSFP_RST - QSFP_LPMODE
 * 	each bit represent the one gpio
 *      exemple: bits[0:15] - bit0 - gpio0
 * QSFP_LED_LANE0_GREEN - QSFP_LED_LANE3_FAULT
 *	here, number represent the one gpio
 * 	exemple: bits[0:1]
 *	00 - gpio off, 01 - gpio on [ gpio0]
 *      00 - gpio off, 10 - gpio on [ gpio1]
 *      00 - gpio off, 11 - gpio on [ gpio2]
 *
 */
enum {
	QSFP_RST,
	QSFP_PRESENT,
	QSFP_PHY_RST,
	QSFP_LPMOD,
	QSFP_LED_LANE0_GREEN,
	QSFP_LED_LANE1_GREEN,
	QSFP_LED_LANE2_GREEN,
	QSFP_LED_LANE3_GREEN,
	QSFP_LED_LANE0_BEACON,
	QSFP_LED_LANE1_BEACON,
	QSFP_LED_LANE2_BEACON,
	QSFP_LED_LANE3_BEACON,
	QSFP_LED_LANE0_FAULT,
	QSFP_LED_LANE1_FAULT,
	QSFP_LED_LANE2_FAULT,
	QSFP_LED_LANE3_FAULT,
	QSFP_LED_LANE0_AMBER,
	QSFP_LED_LANE1_AMBER,
	QSFP_LED_LANE2_AMBER,
	QSFP_LED_LANE3_AMBER,
	TMC_PFE_GPIO_GROUP_MAX
};

enum sfp_op {
	SFP_TX_DISABLE,
	SFP_LED_ACTIVITY,
	SFP_PRESENT,
	SFP_SFP_LOS,
	SFP_TX_FAULT,
	SFP_LED_LANE0_GREEN = SFP_LED_OP_START_INDEX,
	SFP_LED_LANE1_GREEN,
	SFP_LED_LANE2_GREEN,
	SFP_LED_LANE3_GREEN,
	SFP_LED_LANE0_BEACON,
	SFP_LED_LANE1_BEACON,
	SFP_LED_LANE2_BEACON,
	SFP_LED_LANE3_BEACON,
	SFP_LED_LANE0_FAULT,
	SFP_LED_LANE1_FAULT,
	SFP_LED_LANE2_FAULT,
	SFP_LED_LANE3_FAULT,
	SFP_LED_LANE0_AMBER,
	SFP_LED_LANE1_AMBER,
	SFP_LED_LANE2_AMBER,
	SFP_LED_LANE3_AMBER,
	TMC_PFE_SFP_GPIO_GROUP_MAX
};

enum {
	XMC_SFP_TX_DISABLE,
	XMC_SFP_PRESENT,
	XMC_SFP_TX_FAULT,
	XMC_SFP_SFP_LOS,
	XMC_PORT_LED_ACTIVITY,
	XMC_PORT_SW_LED_ACTIVITY,
	XMC_QSFP_LPMOD,
	XMC_PORT_LED_GREEN,
	XMC_PORT_LED_BEACON,
	XMC_PORT_LED_FAULT,
	XMC_PORT_LED_MFGTEST,
	XMC_SFP_MAINBOARD_PRESENT,
	XMC_SFP_MAINBOARD_TXDISABLE,
	XMC_PFE_GPIO_GROUP_MAX
};

enum {
	TXMC_QSFP_PWR_GOOD_STATUS0, /* QSFP PWRGOOD groups start */
	TXMC_QSFP_PWR_GOOD_STATUS1,
	TXMC_QSFP_RESET,  /* QSFP groups start */
	TXMC_QSFP_PRESENT,
	TXMC_QSFP_LED_GREEN,
	TXMC_QSFP_LED_FAULT,
	TXMC_QSFP_LED_AMBER,
	TXMC_QSFP_LED_GREEN_BEACON,
	TXMC_QSFP_LED_FAULT_BEACON,
	TXMC_QSFP_LED_AMBER_BEACON,
	TXMC_QSFP_LED_MFGTEST,
	TXMC_QSFP_GPIO_GROUP_MAX
};

enum txmc_sfp_op {
	TXMC_SFP_TX_DISABLE, /* SFP groups start */
	TXMC_SFP_PRESENT,
	TXMC_SFP_TX_FAULT,
	TXMC_SFP_SFP_LOS,
	TXMC_SFP_LED_GREEN = TXMC_QSFP_GPIO_GROUP_MAX,
	TXMC_SFP_LED_FAULT,
	TXMC_SFP_LED_AMBER,
	TXMC_SFP_LED_GREEN_BEACON,
	TXMC_SFP_LED_FAULT_BEACON,
	TXMC_SFP_LED_AMBER_BEACON,
	TXMC_SFP_GPIO_GROUP_MAX
};

enum txmc_extdev_op {
	TXMC_PORTCPLD0_RESET, /* EXTDEV op start */
	TXMC_PORTCPLD1_RESET,
	TXMC_PFE_PCIE_RESET,
	TXMC_PFE_SYS_RESET,
	TXMC_PFE_JTAG_RESET,
	TXMC_PORTCPLD2_RESET,
	TXMC_EXTDEV_GPIO_GROUP_MAX
};

static const u32 group_offset[TMC_PFE_GPIO_GROUP_MAX] = {
			TMC_PFE_QSFP_RESET_OFFSET,
			TMC_PFE_QSFP_PRESENT_OFFSET,
			TMC_PFE_QSFP_PHY_RESET_OFFSET,
			TMC_PFE_QSFP_LPMOD_OFFSET,
			TMC_PFE_QSFP_LED_CTRL_OFFSET, /* LANE0 GREEN */
			TMC_PFE_QSFP_LED_CTRL_OFFSET, /* LANE1 GREEN */
			TMC_PFE_QSFP_LED_CTRL_OFFSET, /* LANE2 GREEN */
			TMC_PFE_QSFP_LED_CTRL_OFFSET, /* LANE3 GREEN */
			TMC_PFE_QSFP_LED_CTRL_OFFSET, /* LANE0 BEACON */
			TMC_PFE_QSFP_LED_CTRL_OFFSET, /* LANE1 BEACON */
			TMC_PFE_QSFP_LED_CTRL_OFFSET, /* LANE2 BEACON */
			TMC_PFE_QSFP_LED_CTRL_OFFSET, /* LANE3 BEACON */
			TMC_PFE_QSFP_LED_CTRL_OFFSET, /* LANE0 FAULT */
			TMC_PFE_QSFP_LED_CTRL_OFFSET, /* LANE1 FAULT */
			TMC_PFE_QSFP_LED_CTRL_OFFSET, /* LANE2 FAULT */
			TMC_PFE_QSFP_LED_CTRL_OFFSET, /* LANE3 FAULT */
			TMC_PFE_QSFP_LED_CTRL_OFFSET, /* LANE0 AMBER */
			TMC_PFE_QSFP_LED_CTRL_OFFSET, /* LANE1 AMBER */
			TMC_PFE_QSFP_LED_CTRL_OFFSET, /* LANE2 AMBER */
			TMC_PFE_QSFP_LED_CTRL_OFFSET, /* LANE3 AMBER */
};

static const u32 sfp_slaveb0_group_offset[TMC_PFE_SFP_GPIO_GROUP_MAX] = {
			TMC_PFE_SFPSB0_TX_DISABLE_OFFSET,
			TMC_PFE_SFPSB0_LED_ACTIVITY_OFFSET,
			TMC_PFE_SFPSB0_PRESENT_OFFSET,
			TMC_PFE_SFPSB0_LOSS_OFFSET,
			TMC_PFE_SFPSB0_TX_FAULT_OFFSET,
			TMC_PFE_SFPSB0_LED_CTRL_OFFSET, /* LANE0 GREEN */
			TMC_PFE_SFPSB0_LED_CTRL_OFFSET, /* LANE1 GREEN */
			TMC_PFE_SFPSB0_LED_CTRL_OFFSET, /* LANE2 GREEN */
			TMC_PFE_SFPSB0_LED_CTRL_OFFSET, /* LANE3 GREEN */
			TMC_PFE_SFPSB0_LED_CTRL_OFFSET, /* LANE0 BEACON */
			TMC_PFE_SFPSB0_LED_CTRL_OFFSET, /* LANE1 BEACON */
			TMC_PFE_SFPSB0_LED_CTRL_OFFSET, /* LANE2 BEACON */
			TMC_PFE_SFPSB0_LED_CTRL_OFFSET, /* LANE3 BEACON */
			TMC_PFE_SFPSB0_LED_CTRL_OFFSET, /* LANE0 FAULT */
			TMC_PFE_SFPSB0_LED_CTRL_OFFSET, /* LANE1 FAULT */
			TMC_PFE_SFPSB0_LED_CTRL_OFFSET, /* LANE2 FAULT */
			TMC_PFE_SFPSB0_LED_CTRL_OFFSET, /* LANE3 FAULT */
			TMC_PFE_SFPSB0_LED_CTRL_OFFSET, /* LANE0 AMBER */
			TMC_PFE_SFPSB0_LED_CTRL_OFFSET, /* LANE1 AMBER */
			TMC_PFE_SFPSB0_LED_CTRL_OFFSET, /* LANE2 AMBER */
			TMC_PFE_SFPSB0_LED_CTRL_OFFSET, /* LANE3 AMBER */
};

static const u32 sfp_slaveb1_group_offset[TMC_PFE_SFP_GPIO_GROUP_MAX] = {
			TMC_PFE_SFPSB1_TX_DISABLE_OFFSET,
			TMC_PFE_SFPSB1_LED_ACTIVITY_OFFSET,
			TMC_PFE_SFPSB1_PRESENT_OFFSET,
			TMC_PFE_SFPSB1_LOSS_OFFSET,
			TMC_PFE_SFPSB1_TX_FAULT_OFFSET,
			TMC_PFE_SFPSB1_LED_CTRL_OFFSET, /* LANE0 GREEN */
			TMC_PFE_SFPSB1_LED_CTRL_OFFSET, /* LANE1 GREEN */
			TMC_PFE_SFPSB1_LED_CTRL_OFFSET, /* LANE2 GREEN */
			TMC_PFE_SFPSB1_LED_CTRL_OFFSET, /* LANE3 GREEN */
			TMC_PFE_SFPSB1_LED_CTRL_OFFSET, /* LANE0 BEACON */
			TMC_PFE_SFPSB1_LED_CTRL_OFFSET, /* LANE1 BEACON */
			TMC_PFE_SFPSB1_LED_CTRL_OFFSET, /* LANE2 BEACON */
			TMC_PFE_SFPSB1_LED_CTRL_OFFSET, /* LANE3 BEACON */
			TMC_PFE_SFPSB1_LED_CTRL_OFFSET, /* LANE0 FAULT */
			TMC_PFE_SFPSB1_LED_CTRL_OFFSET, /* LANE1 FAULT */
			TMC_PFE_SFPSB1_LED_CTRL_OFFSET, /* LANE2 FAULT */
			TMC_PFE_SFPSB1_LED_CTRL_OFFSET, /* LANE3 FAULT */
			TMC_PFE_SFPSB1_LED_CTRL_OFFSET, /* LANE0 AMBER */
			TMC_PFE_SFPSB1_LED_CTRL_OFFSET, /* LANE1 AMBER */
			TMC_PFE_SFPSB1_LED_CTRL_OFFSET, /* LANE2 AMBER */
			TMC_PFE_SFPSB1_LED_CTRL_OFFSET, /* LANE3 AMBER */
};

static const u32 xmc_group_offset[XMC_PFE_GPIO_GROUP_MAX] = {
			XMC_PFE_SFP_TX_DISABLE_OFFSET,
			XMC_PFE_SFP_PRESENT_OFFSET,
			XMC_PFE_SFP_TX_FAULT_OFFSET,
			XMC_PFE_SFP_LOSS_OFFSET,
			XMC_PFE_LED_ACTIVITY_OFFSET,
			XMC_PFE_SW_LED_ACTIVITY_OFFSET,
			XMC_PFE_QSFP_LPMOD_OFFSET,
			XMC_PFE_PORT_LED_CTRL_OFFSET, /* GREEN */
			XMC_PFE_PORT_LED_CTRL_OFFSET, /* BEACON */
			XMC_PFE_PORT_LED_CTRL_OFFSET, /* FAULT */
			XMC_PFE_PORT_LED_CTRL_OFFSET, /* MFG Test */
			XMC_PFE_SFP_MAINBOARD_PRESENT,
			XMC_PFE_SFP_MAINBOARD_TXDISABLE,
};

static const u32 txmc_group_offset[TXMC_QSFP_GPIO_GROUP_MAX] = {
			TXMC_PFE_QSFP_PWR_GOOD_STATUS0, /* PowerGood status for port 0-31  */
			TXMC_PFE_QSFP_PWR_GOOD_STATUS1, /* PowerGood status for port 32-63 */
			TXMC_PFE_QSFP_RESET_OFFSET,
			TXMC_PFE_QSFP_PRESENT_OFFSET,
			TXMC_PFE_PORT_LED_CTRL_OFFSET,  /* GREEN */
			TXMC_PFE_PORT_LED_CTRL_OFFSET,  /* FAULT */
			TXMC_PFE_PORT_LED_CTRL_OFFSET,  /* AMBER */
			TXMC_PFE_PORT_LED_CTRL_OFFSET,  /* GREEN BEACON */
			TXMC_PFE_PORT_LED_CTRL_OFFSET,  /* FAULT BEACON */
			TXMC_PFE_PORT_LED_CTRL_OFFSET,  /* AMBER BEACON */
			TXMC_PFE_PORT_LED_CTRL_OFFSET,  /* MFG Test */
};

static const u32 txmc_sfp_group_offset[TXMC_SFP_GPIO_GROUP_MAX] = {
			TXMC_PFE_SFP_TX_DISABLE_OFFSET,
			TXMC_PFE_SFP_PRESENT_OFFSET,
			TXMC_PFE_SFP_TX_FAULT_OFFSET,
			TXMC_PFE_SFP_LOSS_OFFSET,
			TXMC_PFE_SFP_LED_CTRL_OFFSET,
			TXMC_PFE_SFP_LED_CTRL_OFFSET,
			TXMC_PFE_SFP_LED_CTRL_OFFSET,
			TXMC_PFE_SFP_LED_CTRL_OFFSET,
			TXMC_PFE_SFP_LED_CTRL_OFFSET,
			TXMC_PFE_SFP_LED_CTRL_OFFSET,
};

static const u32 txmc_extdev_group_offset[TXMC_EXTDEV_GPIO_GROUP_MAX] = {
			TXMC_EXT_DEVICE_RESET_OFFSET,   /* External device PCPLD0 Reset    */
			TXMC_EXT_DEVICE_RESET_OFFSET,   /* External device PCPLD1 Reset    */
			TXMC_EXT_DEVICE_RESET_OFFSET,   /* External device PFE_PCIE Reset  */
			TXMC_EXT_DEVICE_RESET_OFFSET,   /* External device PFE_SYS Reset   */
			TXMC_EXT_DEVICE_RESET_OFFSET,   /* External device JTAG Reset      */
			TXMC_EXT_DEVICE_RESET_OFFSET,   /* External device PCPLD2 Reset    */
};

struct tmc_gpio_info {
	int (*get)(struct gpio_chip *, unsigned int);
	void (*set)(struct gpio_chip *, unsigned int, int);
	int (*dirin)(struct gpio_chip *, unsigned int);
	int (*dirout)(struct gpio_chip *, unsigned int, int);
	void (*set_multiple)(struct gpio_chip *chip,
			     unsigned long *mask,
			     unsigned long *bits);
};

struct tmc_gpio_chip {
	const struct tmc_gpio_info *info;
	void __iomem *base;
	struct device *dev;
	struct gpio_chip gpio;
	int ngpio;
	spinlock_t gpio_lock; /* gpio lock */
	int sfp_slave_block;
	u32 read_cache;
	bool read_cache_valid;
};

/*
 * generic bit operation functions
 */
static u32 tmc_gpio_reset_bits(u32 state, u32 val, u32 shift)
{
	state &= ~(val << shift);
	return state;
};

static u32 tmc_gpio_set_bits(u32 state, u32 val, u32 shift)
{
	state |= (val << shift);
	return state;
};

static u32 tmc_gpio_find_bits_val(u32 state, u32 shift, u32 mask)
{
	return ((state >> shift)) & mask;
};

#define to_tmc_chip(chip) \
	container_of((chip), struct tmc_gpio_chip, gpio)

/*
 * tmc_gpio_multiple_bitsop - Generic TMC GPIO multiple bits operation
 */
static void tmc_gpio_multiple_bitsop(struct tmc_gpio_chip *chip,
				unsigned int gpiono, u32 group, u32 offset, bool set)
{
	u32 gpio_state, led_val, bit_shift = 0, bit_width = 2, bit_mask = 0x3;
	unsigned long flags;
	int err;
	void __iomem *iobase;

	err = of_property_read_u32((chip->dev)->of_node, "bit-mask", &bit_mask);
	if (err)
		dev_err(chip->dev, "TMC GPIO multiple bitop: No bit-mask entry in gpio chip.\n");

	err = of_property_read_u32((chip->dev)->of_node, "bit-shift", &bit_width);
	if (err)
		dev_err(chip->dev, "TMC GPIO multiple bitop: No bit-shift entry in gpio chip.\n");

	dev_dbg(chip->dev, "TMC GPIO multiple bitop group=%u, "
		"gpiono=%u, offet:=%u, set=%u\n", group, gpiono, offset, set);

	iobase = chip->base + offset;
	spin_lock_irqsave(&chip->gpio_lock, flags);

	switch (group) {
	case QSFP_LED_LANE0_GREEN:
	case SFP_LED_LANE0_GREEN:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		led_val = TMC_PFE_LANES_GREEN_LED_VALUE;
		break;
	case QSFP_LED_LANE1_GREEN:
	case SFP_LED_LANE1_GREEN:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		led_val = TMC_PFE_LANES_GREEN_LED_VALUE;
		bit_shift = 1 * bit_width;
		break;
	case QSFP_LED_LANE2_GREEN:
	case SFP_LED_LANE2_GREEN:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		led_val = TMC_PFE_LANES_GREEN_LED_VALUE;
		bit_shift = 2 * bit_width;
		break;
	case QSFP_LED_LANE3_GREEN:
	case SFP_LED_LANE3_GREEN:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		led_val = TMC_PFE_LANES_GREEN_LED_VALUE;
		bit_shift = 3 * bit_width;
		break;
	case QSFP_LED_LANE0_BEACON:
	case SFP_LED_LANE0_BEACON:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		led_val = TMC_PFE_LANES_BEACON_LED_VALUE;
		break;
	case QSFP_LED_LANE1_BEACON:
	case SFP_LED_LANE1_BEACON:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		led_val = TMC_PFE_LANES_BEACON_LED_VALUE;
		bit_shift = 1 * bit_width;
		break;
	case QSFP_LED_LANE2_BEACON:
	case SFP_LED_LANE2_BEACON:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		led_val = TMC_PFE_LANES_BEACON_LED_VALUE;
		bit_shift = 2 * bit_width;
		break;
	case QSFP_LED_LANE3_BEACON:
	case SFP_LED_LANE3_BEACON:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		led_val = TMC_PFE_LANES_BEACON_LED_VALUE;
		bit_shift = 3 * bit_width;
		break;
	case QSFP_LED_LANE0_FAULT:
	case SFP_LED_LANE0_FAULT:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		led_val = TMC_PFE_LANES_FAULT_LED_VALUE;
		break;
	case QSFP_LED_LANE1_FAULT:
	case SFP_LED_LANE1_FAULT:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		led_val = TMC_PFE_LANES_FAULT_LED_VALUE;
		bit_shift = 1 * bit_width;
		break;
	case QSFP_LED_LANE2_FAULT:
	case SFP_LED_LANE2_FAULT:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		led_val = TMC_PFE_LANES_FAULT_LED_VALUE;
		bit_shift = 2 * bit_width;
		break;
	case QSFP_LED_LANE3_FAULT:
	case SFP_LED_LANE3_FAULT:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		led_val = TMC_PFE_LANES_FAULT_LED_VALUE;
		bit_shift = 3 * bit_width;
		break;
	case QSFP_LED_LANE0_AMBER:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		led_val = TMC_PFE_LANES_AMBER_LED_VALUE;
		break;
	case QSFP_LED_LANE1_AMBER:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		led_val = TMC_PFE_LANES_AMBER_LED_VALUE;
		bit_shift = 1 * bit_width;
		break;
	case QSFP_LED_LANE2_AMBER:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		led_val = TMC_PFE_LANES_AMBER_LED_VALUE;
		bit_shift = 2 * bit_width;
		break;
	case QSFP_LED_LANE3_AMBER:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		led_val = TMC_PFE_LANES_AMBER_LED_VALUE;
		bit_shift = 3 * bit_width;
		break;
	case SFP_LED_LANE0_AMBER:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		led_val = TMC_PFE_LANES_SFP_AMBER_LED_VALUE;
		break;
	case SFP_LED_LANE1_AMBER:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		led_val = TMC_PFE_LANES_SFP_AMBER_LED_VALUE;
		bit_shift = 1 * bit_width;
		break;
	case SFP_LED_LANE2_AMBER:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		led_val = TMC_PFE_LANES_SFP_AMBER_LED_VALUE;
		bit_shift = 2 * bit_width;
		break;
	case SFP_LED_LANE3_AMBER:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		led_val = TMC_PFE_LANES_SFP_AMBER_LED_VALUE;
		bit_shift = 3 * bit_width;
		break;
	default:
		spin_unlock_irqrestore(&chip->gpio_lock, flags);
		return;
	}

	if (set) {
		gpio_state = tmc_gpio_reset_bits(gpio_state, bit_mask, bit_shift);
		gpio_state = tmc_gpio_set_bits(gpio_state, led_val, bit_shift);
	} else {
		gpio_state = tmc_gpio_reset_bits(gpio_state, bit_mask, bit_shift);
	}

	iowrite32(gpio_state, (iobase+(0x004*gpiono)));

	spin_unlock_irqrestore(&chip->gpio_lock, flags);

	return;
};

/*
 * xmc_gpio_multiple_bitsop - Generic XMC GPIO multiple bits operation
 */
static void xmc_gpio_multiple_bitsop(struct tmc_gpio_chip *chip,
				     unsigned int gpiono, u32 group,
				     u32 offset, bool set)
{
	u32 gpio_state, led_val, bshift;
	unsigned long flags;
	void __iomem *iobase;

	iobase = chip->base + offset;

	dev_dbg(chip->dev,
		"XMC GPIO bitop group=%u, gpiono=%u, offset:=%u, set=%u\n",
		group, gpiono, offset, set);

	spin_lock_irqsave(&chip->gpio_lock, flags);

	switch (group) {
	case XMC_PORT_LED_GREEN:
		led_val = XMC_PFE_GREEN_LED_VALUE;
		break;
	case XMC_PORT_LED_BEACON:
		led_val = XMC_PFE_BEACON_LED_VALUE;
		break;
	case XMC_PORT_LED_FAULT:
		led_val = XMC_PFE_FAULT_LED_VALUE;
		break;
	case XMC_PORT_LED_MFGTEST:
		led_val = XMC_PFE_MFGTEST_LED_VALUE;
		break;
	default:
		spin_unlock_irqrestore(&chip->gpio_lock, flags);
		return;
	}

	gpio_state = ioread32(iobase + (0x004 * (gpiono
					/ XMC_MAX_PORT_PER_REG)));
	bshift = (gpiono % XMC_MAX_PORT_PER_REG) * XMC_MAX_BITS_PER_LED;

	if (set) {
		gpio_state = tmc_gpio_reset_bits(gpio_state, 0x7, bshift);
		gpio_state = tmc_gpio_set_bits(gpio_state, led_val, bshift);
	} else {
		gpio_state = tmc_gpio_reset_bits(gpio_state, 0x7, bshift);
	}

	iowrite32(gpio_state, (iobase + (0x004 * (gpiono
						  / XMC_MAX_PORT_PER_REG))));

	spin_unlock_irqrestore(&chip->gpio_lock, flags);

	return;
};

/*
 * txmc_gpio_multiple_bitsop - Generic TXMC GPIO multiple bits operation
 */
static void txmc_gpio_multiple_bitsop(struct tmc_gpio_chip *chip,
				     unsigned int gpiono, u32 group,
				     u32 offset, bool set)
{
	u32 gpio_state, led_val, bshift;
	u32 max_ports_per_reg, max_bits_per_led;
	unsigned long flags;
	void __iomem *iobase;

	iobase = chip->base + offset;
	max_ports_per_reg = TXMC_MAX_PORT_PER_REG;
	max_bits_per_led = TXMC_MAX_BITS_PER_LED;

	dev_dbg(chip->dev,
		"TXMC GPIO bitop group=%u, gpiono=%u, offset:=%u, set=%u\n",
		group, gpiono, offset, set);

	spin_lock_irqsave(&chip->gpio_lock, flags);

	switch (group) {
	case TXMC_SFP_LED_GREEN:
		max_ports_per_reg = 1;
		max_bits_per_led = 0;
	case TXMC_QSFP_LED_GREEN:
		led_val = TXMC_PFE_GREEN_LED_VALUE;
		break;
	case TXMC_SFP_LED_FAULT:
		max_ports_per_reg = 1;
		max_bits_per_led = 0;
	case TXMC_QSFP_LED_FAULT:
		led_val = TXMC_PFE_FAULT_LED_VALUE;
		break;
	case TXMC_SFP_LED_AMBER:
		max_ports_per_reg = 1;
		max_bits_per_led = 0;
	case TXMC_QSFP_LED_AMBER:
		led_val = TXMC_PFE_AMBER_LED_VALUE;
		break;
	case TXMC_SFP_LED_GREEN_BEACON:
		max_ports_per_reg = 1;
		max_bits_per_led = 0;
	case TXMC_QSFP_LED_GREEN_BEACON:
		led_val = TXMC_PFE_GREEN_BEACON_LED_VALUE;
		break;
	case TXMC_SFP_LED_FAULT_BEACON:
		max_ports_per_reg = 1;
		max_bits_per_led = 0;
	case TXMC_QSFP_LED_FAULT_BEACON:
		led_val = TXMC_PFE_FAULT_BEACON_LED_VALUE;
		break;
	case TXMC_SFP_LED_AMBER_BEACON:
		max_ports_per_reg = 1;
		max_bits_per_led = 0;
	case TXMC_QSFP_LED_AMBER_BEACON:
		led_val = TXMC_PFE_AMBER_BEACON_LED_VALUE;
		break;
	case TXMC_QSFP_LED_MFGTEST:
		led_val = TXMC_PFE_MFGTEST_LED_VALUE;
		break;
	default:
		spin_unlock_irqrestore(&chip->gpio_lock, flags);
		return;
	}

	gpio_state = ioread32(iobase + (0x004 * (gpiono
					/ max_ports_per_reg)));
	bshift = (gpiono % max_ports_per_reg) * max_bits_per_led;

	if (set) {
		gpio_state = tmc_gpio_reset_bits(gpio_state, 0x7, bshift);
		gpio_state = tmc_gpio_set_bits(gpio_state, led_val, bshift);
	} else {
		gpio_state = tmc_gpio_reset_bits(gpio_state, 0x7, bshift);
	}

	iowrite32(gpio_state, (iobase + (0x004 * (gpiono
						  / max_ports_per_reg))));

	spin_unlock_irqrestore(&chip->gpio_lock, flags);

	return;
};

/*
 * tmc_gpio_one_bitop - Generic TMC GPIO single bit operation
 */
static void tmc_gpio_one_bitop(struct tmc_gpio_chip *chip,
				unsigned int bit, u32 offset, bool set)
{
	u32 gpio_state;
	unsigned long flags;
	void __iomem *iobase;

	iobase = chip->base + offset;

	dev_dbg(chip->dev, "TMC GPIO one bitop bit=%u, offset=%x, "
		"set=%u\n", bit, offset, set);

	spin_lock_irqsave(&chip->gpio_lock, flags);

	gpio_state = ioread32(iobase);
	if (set)
		gpio_state |= BIT(bit);
	else
		gpio_state &= ~BIT(bit);

	iowrite32(gpio_state, iobase);

	spin_unlock_irqrestore(&chip->gpio_lock, flags);

	return;
}

/*
 * tmc_gpio_get_multiple_bitsop - Generic TMC get GPIO multiple bits operation
 */
static int tmc_gpio_get_multiple_bitsop(struct tmc_gpio_chip *chip,
				unsigned int gpiono, u32 group, u32 offset)
{
	u32 gpio_state, bit_shift = 0, bit_width = 2, bit_mask = 0x3;
	void __iomem *iobase;
	int err;
	iobase = chip->base + offset;

	err = of_property_read_u32((chip->dev)->of_node, "bit-mask", &bit_mask);
	if (err)
		dev_info(chip->dev, "TMC GPIO multiple bitop: No bit-mask entry in dts.\n");

	err = of_property_read_u32((chip->dev)->of_node, "bit-shift", &bit_width);
	if (err)
		dev_info(chip->dev, "TMC GPIO multiple bitop: No bit-shift entry in dts.\n");

	dev_dbg(chip->dev, "TMC GPIO get multiple bitsop group=%u, "
		"gpiono=%u, offset=%u\n", group, gpiono, offset);

	switch (group) {
	case QSFP_LED_LANE0_GREEN:
	case SFP_LED_LANE0_GREEN:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		return (TMC_PFE_LANES_GREEN_LED_VALUE ==
			tmc_gpio_find_bits_val(gpio_state, bit_shift, bit_mask));
	case QSFP_LED_LANE1_GREEN:
	case SFP_LED_LANE1_GREEN:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		bit_shift = 1 * bit_width;
		return (TMC_PFE_LANES_GREEN_LED_VALUE ==
			tmc_gpio_find_bits_val(gpio_state, bit_shift, bit_mask));
	case QSFP_LED_LANE2_GREEN:
	case SFP_LED_LANE2_GREEN:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		bit_shift = 2 * bit_width;
		return (TMC_PFE_LANES_GREEN_LED_VALUE ==
			tmc_gpio_find_bits_val(gpio_state, bit_shift, bit_mask));
	case QSFP_LED_LANE3_GREEN:
	case SFP_LED_LANE3_GREEN:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		bit_shift = 3 * bit_width;
		return (TMC_PFE_LANES_GREEN_LED_VALUE ==
			tmc_gpio_find_bits_val(gpio_state, bit_shift, bit_mask));
	case QSFP_LED_LANE0_BEACON:
	case SFP_LED_LANE0_BEACON:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		return (TMC_PFE_LANES_BEACON_LED_VALUE ==
			tmc_gpio_find_bits_val(gpio_state, bit_shift, bit_mask));
	case QSFP_LED_LANE1_BEACON:
	case SFP_LED_LANE1_BEACON:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		bit_shift = 1 * bit_width;
		return (TMC_PFE_LANES_BEACON_LED_VALUE ==
			tmc_gpio_find_bits_val(gpio_state, bit_shift, bit_mask));
	case QSFP_LED_LANE2_BEACON:
	case SFP_LED_LANE2_BEACON:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		bit_shift = 2 * bit_width;
		return (TMC_PFE_LANES_BEACON_LED_VALUE ==
			tmc_gpio_find_bits_val(gpio_state, bit_shift, bit_mask));
	case QSFP_LED_LANE3_BEACON:
	case SFP_LED_LANE3_BEACON:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		bit_shift = 3 * bit_width;
		return (TMC_PFE_LANES_BEACON_LED_VALUE ==
			tmc_gpio_find_bits_val(gpio_state, bit_shift, bit_mask));
	case QSFP_LED_LANE0_FAULT:
	case SFP_LED_LANE0_FAULT:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		return (TMC_PFE_LANES_FAULT_LED_VALUE ==
			tmc_gpio_find_bits_val(gpio_state, bit_shift, bit_mask));
	case QSFP_LED_LANE1_FAULT:
	case SFP_LED_LANE1_FAULT:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		bit_shift = 1 * bit_width;
		return (TMC_PFE_LANES_FAULT_LED_VALUE ==
			tmc_gpio_find_bits_val(gpio_state, bit_shift, bit_mask));
	case QSFP_LED_LANE2_FAULT:
	case SFP_LED_LANE2_FAULT:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		bit_shift = 2 * bit_width;
		return (TMC_PFE_LANES_FAULT_LED_VALUE ==
			tmc_gpio_find_bits_val(gpio_state, bit_shift, bit_mask));
	case QSFP_LED_LANE3_FAULT:
	case SFP_LED_LANE3_FAULT:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		bit_shift = 3 * bit_width;
		return (TMC_PFE_LANES_FAULT_LED_VALUE ==
			tmc_gpio_find_bits_val(gpio_state, bit_shift, bit_mask));
	case QSFP_LED_LANE0_AMBER:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		return (TMC_PFE_LANES_AMBER_LED_VALUE ==
			tmc_gpio_find_bits_val(gpio_state, bit_shift, bit_mask));
	case QSFP_LED_LANE1_AMBER:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		bit_shift = 1 * bit_width;
		return (TMC_PFE_LANES_AMBER_LED_VALUE ==
			tmc_gpio_find_bits_val(gpio_state, bit_shift, bit_mask));
	case QSFP_LED_LANE2_AMBER:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		bit_shift = 2 * bit_width;
		return (TMC_PFE_LANES_AMBER_LED_VALUE ==
			tmc_gpio_find_bits_val(gpio_state, bit_shift, bit_mask));
	case QSFP_LED_LANE3_AMBER:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		bit_shift = 3 * bit_width;
		return (TMC_PFE_LANES_AMBER_LED_VALUE ==
			tmc_gpio_find_bits_val(gpio_state, bit_shift, bit_mask));
	case SFP_LED_LANE0_AMBER:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		return (TMC_PFE_LANES_SFP_AMBER_LED_VALUE ==
			tmc_gpio_find_bits_val(gpio_state, bit_shift, bit_mask));
	case SFP_LED_LANE1_AMBER:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		bit_shift = 1 * bit_width;
		return (TMC_PFE_LANES_SFP_AMBER_LED_VALUE ==
			tmc_gpio_find_bits_val(gpio_state, bit_shift, bit_mask));
	case SFP_LED_LANE2_AMBER:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		bit_shift = 2 * bit_width;
		return (TMC_PFE_LANES_SFP_AMBER_LED_VALUE ==
			tmc_gpio_find_bits_val(gpio_state, bit_shift, bit_mask));
	case SFP_LED_LANE3_AMBER:
		gpio_state = ioread32(iobase+(0x004*gpiono));
		bit_shift = 3 * bit_width;
		return (TMC_PFE_LANES_SFP_AMBER_LED_VALUE ==
			tmc_gpio_find_bits_val(gpio_state, bit_shift, bit_mask));
	default:
		return 0;
	}
};

/*
 * xmc_gpio_get_multiple_bitsop - Generic XMC get GPIO multiple bits operation
 */
static int xmc_gpio_get_multiple_bitsop(struct tmc_gpio_chip *chip,
					unsigned int gpiono, u32 group,
					u32 offset)
{
	u32 gpio_state, led_val, bshift;
	void __iomem *iobase;

	iobase = chip->base + offset;

	dev_dbg(chip->dev,
		"XMC GPIO get bitsop group=%u, gpiono=%u, offset=%u\n",
		group, gpiono, offset);

	switch (group) {
	case XMC_PORT_LED_GREEN:
		led_val = XMC_PFE_GREEN_LED_VALUE;
		break;
	case XMC_PORT_LED_BEACON:
		led_val = XMC_PFE_BEACON_LED_VALUE;
		break;
	case XMC_PORT_LED_FAULT:
		led_val = XMC_PFE_FAULT_LED_VALUE;
		break;
	case XMC_PORT_LED_MFGTEST:
		led_val = XMC_PFE_MFGTEST_LED_VALUE;
		break;
	default:
		return 0;
	}

	gpio_state = ioread32(iobase + (0x004 * (gpiono
					/ XMC_MAX_PORT_PER_REG)));
	bshift = (gpiono % XMC_MAX_PORT_PER_REG) * XMC_MAX_BITS_PER_LED;
	return (led_val == tmc_gpio_find_bits_val(gpio_state, bshift, 0x7));
};

/*
 * txmc_gpio_get_multiple_bitsop - Generic TXMC get GPIO multiple bits operation
 */
static int txmc_gpio_get_multiple_bitsop(struct tmc_gpio_chip *chip,
					unsigned int gpiono, u32 group,
					u32 offset)
{
	u32 gpio_state, led_val, bshift;
	u32 max_ports_per_reg, max_bits_per_led;
	void __iomem *iobase;

	iobase = chip->base + offset;
	max_ports_per_reg = TXMC_MAX_PORT_PER_REG;
	max_bits_per_led = TXMC_MAX_BITS_PER_LED;

	dev_dbg(chip->dev,
		"TXMC GPIO get bitsop group=%u, gpiono=%u, offset=%u\n",
		group, gpiono, offset);

	switch (group) {
	case TXMC_SFP_LED_GREEN:
		max_ports_per_reg = 1;
		max_bits_per_led = 0;
	case TXMC_QSFP_LED_GREEN:
		led_val = TXMC_PFE_GREEN_LED_VALUE;
		break;
	case TXMC_SFP_LED_FAULT:
		max_ports_per_reg = 1;
		max_bits_per_led = 0;
	case TXMC_QSFP_LED_FAULT:
		led_val = TXMC_PFE_FAULT_LED_VALUE;
		break;
	case TXMC_SFP_LED_AMBER:
		max_ports_per_reg = 1;
		max_bits_per_led = 0;
	case TXMC_QSFP_LED_AMBER:
		led_val = TXMC_PFE_AMBER_LED_VALUE;
		break;
	case TXMC_SFP_LED_GREEN_BEACON:
		max_ports_per_reg = 1;
		max_bits_per_led = 0;
	case TXMC_QSFP_LED_GREEN_BEACON:
		led_val = TXMC_PFE_GREEN_BEACON_LED_VALUE;
		break;
	case TXMC_SFP_LED_FAULT_BEACON:
		max_ports_per_reg = 1;
		max_bits_per_led = 0;
	case TXMC_QSFP_LED_FAULT_BEACON:
		led_val = TXMC_PFE_FAULT_BEACON_LED_VALUE;
		break;
	case TXMC_SFP_LED_AMBER_BEACON:
		max_ports_per_reg = 1;
		max_bits_per_led = 0;
	case TXMC_QSFP_LED_AMBER_BEACON:
		led_val = TXMC_PFE_AMBER_BEACON_LED_VALUE;
		break;
	case TXMC_QSFP_LED_MFGTEST:
		led_val = TXMC_PFE_MFGTEST_LED_VALUE;
		break;
	default:
		return 0;
	}

	gpio_state = ioread32(iobase + (0x004 * (gpiono
					/ max_ports_per_reg)));
	bshift = (gpiono % max_ports_per_reg) * max_bits_per_led;
	return (led_val == tmc_gpio_find_bits_val(gpio_state, bshift, 0x7));
};

/*
 * tmc_gpio_get - Read the specified signal of the GPIO device.
 */
static int tmc_gpio_get(struct gpio_chip *gc, unsigned int gpio)
{
	struct tmc_gpio_chip *chip = to_tmc_chip(gc);
	unsigned int group = TMC_GPIO_FIND_GROUP(gpio);
	unsigned int bit   = TMC_GPIO_FIND_GPIO(gpio);

	if (group >= TMC_PFE_GPIO_GROUP_MAX)
		return 0;

	switch (group) {
	case QSFP_RST:
	case QSFP_PRESENT:
	case QSFP_PHY_RST:
	case QSFP_LPMOD:
		dev_dbg(chip->dev, "TMC GPIO get one bitop group=%u, gpio=%u, "
			"bit=%u\n", group, gpio, bit);
		return !!(ioread32(chip->base + group_offset[group])
				& BIT(bit));
	default:
		return tmc_gpio_get_multiple_bitsop(chip, bit, group, group_offset[group]);
	}
}

/*
 * tmc_gpio_sfp_get - Read the specified signal of the GPIO device.
 */
static int tmc_gpio_sfp_get(struct gpio_chip *gc, unsigned int gpio)
{
	struct tmc_gpio_chip *chip = to_tmc_chip(gc);
	unsigned int group = TMC_GPIO_SFP_FIND_GROUP(gpio);
	unsigned int bit   = TMC_GPIO_SFP_FIND_GPIO(gpio);
	enum sfp_op sfp_group;
	u32 sfp_offset;

	if (group >= TMC_PFE_SFP_GPIO_GROUP_MAX)
		return 0;

	sfp_group = group;
	switch (sfp_group) {
	case SFP_TX_DISABLE:
	case SFP_LED_ACTIVITY:
	case SFP_PRESENT:
	case SFP_SFP_LOS:
	case SFP_TX_FAULT:
		dev_dbg(chip->dev, "TMC GPIO get one bitop group=%u, gpio=%u, "
			"bit=%u\n", group, gpio, bit);
		if (chip->sfp_slave_block == SFP_SLAVE0_BLOCK) {
			sfp_offset = sfp_slaveb0_group_offset[group];
		} else if (chip->sfp_slave_block == SFP_SLAVE1_BLOCK) {
			sfp_offset = sfp_slaveb1_group_offset[group];
		} else {
			sfp_offset = sfp_slaveb0_group_offset[group];
		}
		return !!(ioread32(chip->base + sfp_offset) & BIT(bit));
	default:
		if (chip->sfp_slave_block == SFP_SLAVE0_BLOCK) {
			sfp_offset = sfp_slaveb0_group_offset[group-SFP_LED_OP_OFFSET];
		} else if (chip->sfp_slave_block == SFP_SLAVE1_BLOCK) {
			sfp_offset = sfp_slaveb1_group_offset[group-SFP_LED_OP_OFFSET];
		} else {
			/* keep slave block 1 as default */
			sfp_offset = sfp_slaveb1_group_offset[group-SFP_LED_OP_OFFSET];
		}
		return tmc_gpio_get_multiple_bitsop(chip, bit, group, sfp_offset);
	}
}

/*
 * tmc_gpio_ds100_mux_get - Read the specified signal of the GPIO device.
 */
static int tmc_gpio_ds100_mux_get(struct gpio_chip *gc, unsigned int gpio)
{
	struct tmc_gpio_chip *chip = to_tmc_chip(gc);
	unsigned int bit = TMC_GPIO_FIND_GPIO(gpio);

	dev_dbg(chip->dev, "TMC MUX GPIO get gpio=%u, " "bit=%u\n", gpio, bit);
	return !!(ioread32(chip->base) & BIT(bit));
}

/*
 * tmc_gpio_ptp_get - Read the specified signal of the GPIO device.
 */
static int tmc_gpio_ptp_get(struct gpio_chip *gc, unsigned int gpio)
{
	struct tmc_gpio_chip *chip = to_tmc_chip(gc);
	unsigned int bit = TMC_GPIO_PTPCFG_FIND_GPIO(gpio);

	dev_dbg(chip->dev, "PTPCFG GPIO get gpio=%u, bit=%u\n", gpio, bit);
	chip->read_cache_valid = false;
	return !!(ioread32(chip->base) & BIT(bit));
}

/*
 * xmc_gpio_get - Read the specified signal of the GPIO device.
 */
static int xmc_gpio_get(struct gpio_chip *gc, unsigned int gpio)
{
	struct tmc_gpio_chip *chip = to_tmc_chip(gc);
	unsigned int group = XMC_GPIO_FIND_GROUP(gpio);
	unsigned int bit   = XMC_GPIO_FIND_GPIO(gpio);

	if (group >= XMC_PFE_GPIO_GROUP_MAX)
		return 0;

	switch (group) {
	case XMC_SFP_TX_DISABLE:
	case XMC_SFP_PRESENT:
	case XMC_SFP_TX_FAULT:
	case XMC_SFP_SFP_LOS:
	case XMC_PORT_LED_ACTIVITY:
	case XMC_PORT_SW_LED_ACTIVITY:
	case XMC_QSFP_LPMOD:
	case XMC_SFP_MAINBOARD_PRESENT:
	case XMC_SFP_MAINBOARD_TXDISABLE:
		dev_dbg(chip->dev,
			"XMC GPIO get one bitop group=%u, gpio=%u, bit=%u\n",
			group, gpio, bit);
		return !!(ioread32(chip->base + xmc_group_offset[group])
			  & BIT(bit));
	default:
		return xmc_gpio_get_multiple_bitsop(chip, bit, group,
						    xmc_group_offset[group]);
	}
}

/*
 * txmc_gpio_get - Read the specified signal of the GPIO device.
 */
static int txmc_gpio_get(struct gpio_chip *gc, unsigned int gpio)
{
	struct tmc_gpio_chip *chip = to_tmc_chip(gc);
	unsigned int group = TXMC_GPIO_FIND_GROUP(gpio);
	unsigned int bit   = TXMC_GPIO_FIND_GPIO(gpio);

	if (group >= TXMC_QSFP_GPIO_GROUP_MAX)
		return 0;

	switch (group) {
	case TXMC_QSFP_RESET:
	case TXMC_QSFP_PRESENT:
	case TXMC_QSFP_PWR_GOOD_STATUS0:
	case TXMC_QSFP_PWR_GOOD_STATUS1:
		dev_dbg(chip->dev,
			"TXMC GPIO get one bitop group=%u, gpio=%u, bit=%u\n",
			group, gpio, bit);
		return !!(ioread32(chip->base + txmc_group_offset[group])
			  & BIT(bit));
	default:
		return txmc_gpio_get_multiple_bitsop(chip, bit, group,
					txmc_group_offset[group]);
	}
}

/*
 * txmc_gpio_sfp_get - Read the specified signal of the GPIO device.
 */
static int txmc_gpio_sfp_get(struct gpio_chip *gc, unsigned int gpio)
{
	struct tmc_gpio_chip *chip = to_tmc_chip(gc);
	unsigned int group = TXMC_GPIO_SFP_FIND_GROUP(gpio);
	unsigned int bit   = TXMC_GPIO_SFP_FIND_GPIO(gpio);

	if (group >= TXMC_SFP_GPIO_GROUP_MAX)
		return 0;

	switch (group) {
	case TXMC_SFP_TX_DISABLE:
	case TXMC_SFP_PRESENT:
	case TXMC_SFP_TX_FAULT:
	case TXMC_SFP_SFP_LOS:
		dev_dbg(chip->dev,
			"TXMC GPIO sfp get one bitop group=%u, gpio=%u, bit=%u\n",
			group, gpio, bit);
		return !!(ioread32(chip->base + txmc_sfp_group_offset[group])
			  & BIT(bit));
	default:
		return txmc_gpio_get_multiple_bitsop(chip, bit, group,
						    txmc_sfp_group_offset[group - TXMC_SFP_LED_OP_OFFSET]);
	}
}

/*
 * txmc_gpio_dev_get - Read the specified signal of the GPIO device.
 */
static int txmc_gpio_dev_get(struct gpio_chip *gc, unsigned int gpio)
{
	struct tmc_gpio_chip *chip = to_tmc_chip(gc);
	unsigned int group = TXMC_GPIO_DEV_FIND_GROUP(gpio);
	unsigned int bit   = TXMC_GPIO_DEV_FIND_GPIO(gpio);

	if (group >= TXMC_EXTDEV_GPIO_GROUP_MAX)
		return 0;

	switch (group) {
	case TXMC_PORTCPLD2_RESET:
		bit = 15; //get bit 15 for cpld2 reset bit.
	case TXMC_PORTCPLD0_RESET:
	case TXMC_PORTCPLD1_RESET:
	case TXMC_PFE_PCIE_RESET:
	case TXMC_PFE_SYS_RESET:
	case TXMC_PFE_JTAG_RESET:
		dev_dbg(chip->dev,
			"TXMC GPIO external dev get one bitop group=%u, gpio=%u, bit=%u\n",
			group, gpio, bit);
		return !!(ioread32(chip->base + txmc_extdev_group_offset[group])
			  & BIT(bit));
	default:
		return 0;
	}
}

/*
 * tmc_gpio_set - Write the specified signal of the GPIO device.
 */
static void tmc_gpio_set(struct gpio_chip *gc, unsigned int gpio, int val)
{
	struct tmc_gpio_chip *chip = to_tmc_chip(gc);
	unsigned int group = TMC_GPIO_FIND_GROUP(gpio);
	unsigned int bit   = TMC_GPIO_FIND_GPIO(gpio);

	if (group >= TMC_PFE_GPIO_GROUP_MAX)
		return;

	switch (group) {
	case QSFP_RST:
	case QSFP_PRESENT:
	case QSFP_PHY_RST:
	case QSFP_LPMOD:
		dev_dbg(chip->dev, "TMC GPIO one bitop group=%d\n", group);
		tmc_gpio_one_bitop(chip, bit, group_offset[group], val);
		break;
	default:
		tmc_gpio_multiple_bitsop(chip, bit, group, group_offset[group], val);
		break;
	}
}

/*
 * tmc_gpio_sfp_set - Write the specified signal of the GPIO device.
 */
static void tmc_gpio_sfp_set(struct gpio_chip *gc, unsigned int gpio, int val)
{
	struct tmc_gpio_chip *chip = to_tmc_chip(gc);
	unsigned int group = TMC_GPIO_SFP_FIND_GROUP(gpio);
	unsigned int bit   = TMC_GPIO_SFP_FIND_GPIO(gpio);
	enum sfp_op sfp_group;
	u32 sfp_offset;

	if (group >= TMC_PFE_SFP_GPIO_GROUP_MAX)
		return;

	sfp_group = group;
	switch (sfp_group) {
	case SFP_TX_DISABLE:
	case SFP_LED_ACTIVITY:
	case SFP_PRESENT:
	case SFP_SFP_LOS:
	case SFP_TX_FAULT:
		dev_dbg(chip->dev, "TMC GPIO one bitop group=%d\n", group);
		if (chip->sfp_slave_block == SFP_SLAVE0_BLOCK) {
			sfp_offset = sfp_slaveb0_group_offset[group];
		} else if (chip->sfp_slave_block == SFP_SLAVE1_BLOCK) {
			sfp_offset = sfp_slaveb1_group_offset[group];
		} else {
			sfp_offset = sfp_slaveb0_group_offset[group];
		}
		tmc_gpio_one_bitop(chip, bit, sfp_offset, val);
		break;
	default:
		if (chip->sfp_slave_block == SFP_SLAVE0_BLOCK) {
			sfp_offset = sfp_slaveb0_group_offset[group-SFP_LED_OP_OFFSET];
		} else if (chip->sfp_slave_block == SFP_SLAVE1_BLOCK) {
			sfp_offset = sfp_slaveb1_group_offset[group-SFP_LED_OP_OFFSET];
		} else {
			/* keep slave block 1 as default */
			sfp_offset = sfp_slaveb1_group_offset[group-SFP_LED_OP_OFFSET];
		}
		tmc_gpio_multiple_bitsop(chip, bit, group, sfp_offset, val);
		break;
	}
}

/*
 * tmc_gpio_ds100_mux_set - Write the specified signal of the GPIO device.
 */
static void tmc_gpio_ds100_mux_set(struct gpio_chip *gc, unsigned int gpio, int val)
{
	struct tmc_gpio_chip *chip = to_tmc_chip(gc);
	unsigned int bit = TMC_GPIO_FIND_GPIO(gpio);
	u32 gpio_state;
	unsigned long flags;
	void __iomem *iobase;

	iobase = chip->base;

	dev_dbg(chip->dev, "TMC MUX gpio=%u, bit=%u\n", gpio, bit);
	spin_lock_irqsave(&chip->gpio_lock, flags);

	gpio_state = ioread32(iobase);
	if (val)
		gpio_state |= BIT(bit);
	else
		gpio_state &= ~BIT(bit);

	iowrite32(gpio_state, iobase);

	spin_unlock_irqrestore(&chip->gpio_lock, flags);

	return;
}

/*
 * tmc_gpio_ptp_set - Write the specified signal of the GPIO device.
 */
static void tmc_gpio_ptp_set(struct gpio_chip *gc, unsigned int gpio, int val)
{
	struct tmc_gpio_chip *chip = to_tmc_chip(gc);
	unsigned int bit = TMC_GPIO_PTPCFG_FIND_GPIO(gpio);
	u32 gpio_state;
	unsigned long flags;
	void __iomem *iobase;

	iobase = chip->base;

	dev_dbg(chip->dev, "TMC PTP SET gpio=%u, bit=%u\n", gpio, bit);
	spin_lock_irqsave(&chip->gpio_lock, flags);
	if (chip->read_cache_valid)
		gpio_state = chip->read_cache;
	else
		gpio_state = ioread32(iobase);

	if (val)
		gpio_state |= BIT(bit);
	else
		gpio_state &= ~BIT(bit);

	iowrite32(gpio_state, iobase);

	chip->read_cache = gpio_state;
	chip->read_cache_valid = true;

	spin_unlock_irqrestore(&chip->gpio_lock, flags);

	return;
}

/*
 * tmc_gpio_ptp_set_multiple - Write the multiple signals of the GPIO device.
 */
static void tmc_gpio_ptp_data_set_multiple(struct gpio_chip *gc,
					   unsigned long *mask,
					   unsigned long *bits)

{
	struct tmc_gpio_chip *chip = to_tmc_chip(gc);
	unsigned long flags;
	void __iomem *iobase;
	unsigned int mask32 = 0, data32 = 0;
	unsigned int data = 0;

	/* Get num gpios and num of groups */
	/* In case of PTP- TMC reg; only one group*/
	mask32 = mask[0] & TMC_GPIO_PTPDATA_SET_MASK_PER_REG;
	data32 = bits[0] & mask32;
	iobase = chip->base;

	spin_lock_irqsave(&chip->gpio_lock, flags);
	/* If mask covering all reg bits, ignore read Operation */
	if (mask32 == TMC_GPIO_PTPDATA_SET_MASK_PER_REG)  {
		iowrite32(data32, iobase);
	} else {
		data = ioread32(iobase);
		data &= ~mask32; /* clear all masked one */
		data32 |= data; /* retain non masked bits */
		iowrite32(data32, iobase);
	}
	chip->read_cache_valid = false;
	spin_unlock_irqrestore(&chip->gpio_lock, flags);
}

/*
 * xmc_gpio_set - Write the specified signal of the GPIO device.
 */
static void xmc_gpio_set(struct gpio_chip *gc, unsigned int gpio, int val)
{
	struct tmc_gpio_chip *chip = to_tmc_chip(gc);
	unsigned int group = XMC_GPIO_FIND_GROUP(gpio);
	unsigned int bit   = XMC_GPIO_FIND_GPIO(gpio);

	if (group >= XMC_PFE_GPIO_GROUP_MAX)
		return;

	switch (group) {
	case XMC_SFP_TX_DISABLE:
	case XMC_SFP_PRESENT:
	case XMC_SFP_TX_FAULT:
	case XMC_SFP_SFP_LOS:
	case XMC_PORT_LED_ACTIVITY:
	case XMC_PORT_SW_LED_ACTIVITY:
	case XMC_QSFP_LPMOD:
	case XMC_SFP_MAINBOARD_TXDISABLE:
		dev_dbg(chip->dev, "XMC GPIO one bitop group=%d\n", group);
		tmc_gpio_one_bitop(chip, bit, xmc_group_offset[group], val);
		break;
	default:
		xmc_gpio_multiple_bitsop(chip, bit, group,
					 xmc_group_offset[group], val);
		break;
	}
}

/*
 * txmc_gpio_set - Write the specified signal of the GPIO device.
 */
static void txmc_gpio_set(struct gpio_chip *gc, unsigned int gpio, int val)
{
	struct tmc_gpio_chip *chip = to_tmc_chip(gc);
	unsigned int group = TXMC_GPIO_FIND_GROUP(gpio);
	unsigned int bit   = TXMC_GPIO_FIND_GPIO(gpio);

	if (group >= TXMC_QSFP_GPIO_GROUP_MAX)
		return;

	switch (group) {
	case TXMC_QSFP_RESET:
		dev_dbg(chip->dev, "TXMC GPIO one bitop group=%d\n", group);
		tmc_gpio_one_bitop(chip, bit, txmc_group_offset[group], val);
		break;
	case TXMC_QSFP_PRESENT:
	case TXMC_QSFP_PWR_GOOD_STATUS0:
	case TXMC_QSFP_PWR_GOOD_STATUS1:
		break;
	default:
		txmc_gpio_multiple_bitsop(chip, bit, group,
					txmc_group_offset[group], val);
		break;
	}
}

/*
 * txmc_gpio_sfp_set - Write the specified signal of the GPIO device.
 */
static void txmc_gpio_sfp_set(struct gpio_chip *gc, unsigned int gpio, int val)
{
	struct tmc_gpio_chip *chip = to_tmc_chip(gc);
	unsigned int group = TXMC_GPIO_SFP_FIND_GROUP(gpio);
	unsigned int bit   = TXMC_GPIO_SFP_FIND_GPIO(gpio);

	if (group >= TXMC_SFP_GPIO_GROUP_MAX)
		return;

	switch (group) {
	case TXMC_SFP_TX_DISABLE:
	case TXMC_SFP_PRESENT:
	case TXMC_SFP_TX_FAULT:
	case TXMC_SFP_SFP_LOS:
		dev_dbg(chip->dev, "TXMC GPIO sfp one bitop group=%d\n", group);
		tmc_gpio_one_bitop(chip, bit, txmc_sfp_group_offset[group], val);
		break;
	default:
		txmc_gpio_multiple_bitsop(chip, bit, group,
					 txmc_sfp_group_offset[group - TXMC_SFP_LED_OP_OFFSET], val);
		break;
	}
}


/*
 * txmc_gpio_dev_set - Write the specified signal of the GPIO device.
 */
static void txmc_gpio_dev_set(struct gpio_chip *gc, unsigned int gpio, int val)
{
	struct tmc_gpio_chip *chip = to_tmc_chip(gc);
	unsigned int group = TXMC_GPIO_DEV_FIND_GROUP(gpio);
	unsigned int bit   = TXMC_GPIO_DEV_FIND_GPIO(gpio);

	if (group >= TXMC_EXTDEV_GPIO_GROUP_MAX)
		return;

	switch (group) {
	case TXMC_PORTCPLD2_RESET:
        bit = 15; // Set bit 15 for cpld2 reset
	case TXMC_PORTCPLD0_RESET:
	case TXMC_PORTCPLD1_RESET:
	case TXMC_PFE_PCIE_RESET:
	case TXMC_PFE_SYS_RESET:
	case TXMC_PFE_JTAG_RESET:
		dev_dbg(chip->dev, "TXMC GPIO external device one bitop group=%d\n", group);
		tmc_gpio_one_bitop(chip, bit, txmc_extdev_group_offset[group], val);
		break;
	default:
		break;
	}
}

/*
 * tmc_gpio_dir_in_dummy - Write the dir-in setting of GPIO device.
 */
static int tmc_gpio_dir_in_dummy(struct gpio_chip *gc, unsigned int gpio)
{
	return 0;
}

/*
 * tmc_gpio_dir_out_dummy - Write the dir-out setting of the GPIO device.
 */
static int tmc_gpio_dir_out_dummy(struct gpio_chip *gc,
				unsigned int gpio,
				int val)
{
	return 0;
}

static struct tmc_gpio_info tmc_gpios[] = {
	{
	    .get = tmc_gpio_get,
	    .set = tmc_gpio_set,
	},
	{
	    .get = tmc_gpio_sfp_get,
	    .set = tmc_gpio_sfp_set,
	},
	{
	    .get = tmc_gpio_ds100_mux_get,
	    .set = tmc_gpio_ds100_mux_set,
	},
	{
	    .get = tmc_gpio_ptp_get,
	    .set = tmc_gpio_ptp_set,
	    .dirin = tmc_gpio_dir_in_dummy,
	    .dirout = tmc_gpio_dir_out_dummy,
	},
	{
	    .get = tmc_gpio_ptp_get,
	    .set = tmc_gpio_ptp_set,
	    .dirin = tmc_gpio_dir_in_dummy,
	    .dirout = tmc_gpio_dir_out_dummy,
	},
	{
	    .get = tmc_gpio_ptp_get,
	    .set = tmc_gpio_ptp_set,
	    .dirin = tmc_gpio_dir_in_dummy,
	    .dirout = tmc_gpio_dir_out_dummy,
	    .set_multiple = tmc_gpio_ptp_data_set_multiple,
	},
	{
	    .get = xmc_gpio_get,
	    .set = xmc_gpio_set,
	},
	{
	    .get = txmc_gpio_get,
	    .set = txmc_gpio_set,
	},
	{
	    .get = txmc_gpio_sfp_get,
	    .set = txmc_gpio_sfp_set,
	},
	{
	    .get = txmc_gpio_dev_get,
	    .set = txmc_gpio_dev_set,
	}
};

static void tmc_gpio_setup(struct tmc_gpio_chip *sgc)
{
	struct gpio_chip *chip = &sgc->gpio;
	const struct tmc_gpio_info *info = sgc->info;

	chip->get		= info->get;
	chip->set		= info->set;
	chip->direction_input	= info->dirin;
	chip->direction_output	= info->dirout;
	chip->set_multiple	= info->set_multiple;
	chip->dbg_show		= NULL;
	chip->can_sleep		= 0;

	chip->base	= -1;
	chip->ngpio	= sgc->ngpio;
	chip->label	= dev_name(sgc->dev);
	chip->parent	= sgc->dev;
	chip->of_node	= sgc->dev->of_node;
	chip->owner	= THIS_MODULE;
}

static const struct of_device_id tmc_gpio_ids[] = {
	{ .compatible = "jnx,gpioslave0-tmc", .data = &tmc_gpios[0] },
	{ .compatible = "jnx,gpioslave1-tmc", .data = &tmc_gpios[0] },
	{ .compatible = "jnx,gpioslave2-tmc", .data = &tmc_gpios[0] },
	{ .compatible = "jnx,gpioslave3-tmc", .data = &tmc_gpios[0] },
	{ .compatible = "jnx,gpioslave0-sfp-tmc", .data = &tmc_gpios[1] },
	{ .compatible = "jnx,gpioslave1-sfp-tmc", .data = &tmc_gpios[1] },
	{ .compatible = "jnx,ds100-mux-tmc", .data = &tmc_gpios[2] },
	{ .compatible = "jnx,ptp-clk-mux-tmc", .data = &tmc_gpios[2] },
	{ .compatible = "jnx,clk-mux-tmc", .data = &tmc_gpios[2] },
	{ .compatible = "jnx,pll-status-tmc", .data = &tmc_gpios[2] },
	{ .compatible = "jnx,ptpcfg-tmc", .data = &tmc_gpios[3] },
	{ .compatible = "jnx,ptpreset-tmc", .data = &tmc_gpios[4] },
	{ .compatible = "jnx,extdevreset-xmc", .data = &tmc_gpios[4] },
	{ .compatible = "jnx,ptpdata-tmc", .data = &tmc_gpios[5] },
	{ .compatible = "jnx,gpioslave0-xmc", .data = &tmc_gpios[6] },
	{ .compatible = "jnx,gpioslave1-xmc", .data = &tmc_gpios[6] },
	{ .compatible = "jnx,gpioslave0-txmc", .data = &tmc_gpios[7] },
	{ .compatible = "jnx,gpioslave1-txmc", .data = &tmc_gpios[7] },
	{ .compatible = "jnx,gpioslave2-txmc", .data = &tmc_gpios[7] },
	{ .compatible = "jnx,gpioslave1-sfp-txmc", .data = &tmc_gpios[8]},
	{ .compatible = "jnx,extdevreset-txmc", .data = &tmc_gpios[9] },
	{ },
};
MODULE_DEVICE_TABLE(of, tmc_gpio_ids);

static int tmc_gpio_of_init(struct device *dev,
				struct tmc_gpio_chip *chip)
{
	int err;
	u32 val;
	const struct of_device_id *of_id;

	if (!dev->of_node) {
		dev_err(dev, "No device node\n");
		return -ENODEV;
	}

	of_id = of_match_device(tmc_gpio_ids, dev);
	if (!of_id)
		return -ENODEV;
	chip->info = of_id->data;


	err = of_property_read_u32(dev->of_node, "gpio-count", &val);
	if (!err) {
		if (val > TMC_GPIO_MAX_NGPIO_PER_GROUP)
			val = TMC_GPIO_MAX_NGPIO_PER_GROUP;
		chip->ngpio = val;
	}

	return err;
}

static int tmc_gpio_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct tmc_gpio_chip *chip;
	struct resource *res;
	int ret;

	dev_info(dev, "TMC GPIO probe\n");

	chip = devm_kzalloc(dev, sizeof(*chip), GFP_KERNEL);
	if (!chip)
		return -ENOMEM;

	res = platform_get_resource(pdev, IORESOURCE_MEM, 0);
	if (!res)
		return -ENODEV;

	dev_info(dev, "TMC GPIO resource 0x%llx, %llu\n",
		 res->start, resource_size(res));

	chip->base = devm_ioremap(dev, res->start, resource_size(res));
	if (!chip->base)
		return -ENOMEM;

	ret = tmc_gpio_of_init(dev, chip);
	if (ret)
		return ret;

	chip->dev = dev;
	spin_lock_init(&chip->gpio_lock);

	tmc_gpio_setup(chip);

	ret = gpiochip_add(&chip->gpio);
	if (ret) {
		dev_err(dev,
			"Failed to register TMC gpiochip : %d\n", ret);
		return ret;
	}

	platform_set_drvdata(pdev, chip);
	dev_info(dev, "TMC GPIO registered at 0x%lx, gpiobase: %d\n",
		 (long unsigned)chip->base, chip->gpio.base);

	/* Fetch SFP slave block data from Device Tree if present */
	if (dev->of_node) {
		of_property_read_u32(dev->of_node,
			"sfp-slave-block", &chip->sfp_slave_block);
	}

	return 0;
}

static int tmc_gpio_remove(struct platform_device *pdev)
{
	struct tmc_gpio_chip *chip = platform_get_drvdata(pdev);

	gpiochip_remove(&chip->gpio);

	return 0;
}

static struct platform_driver tmc_gpio_driver = {
	.driver = {
		.name = "gpio-tmc",
		.owner  = THIS_MODULE,
		.of_match_table = tmc_gpio_ids,
	},
	.probe = tmc_gpio_probe,
	.remove = tmc_gpio_remove,
};

module_platform_driver(tmc_gpio_driver);

MODULE_DESCRIPTION("Juniper TMC FPGA GPIO driver");
MODULE_AUTHOR("Ashish Bhensdadia <bashish@juniper.net>");
MODULE_LICENSE("GPL");
