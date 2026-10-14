/*
 * Juniper TMC MFD Core driver
 *
 * drivers/mfd/jnx-tmc-core.c
 *
 * This driver is being adpoted from supercon FPGA driver.
 *
 * Copyright (c) 2018, Juniper Networks
 * Author: Ashish Bhensdadia <bashish@juniper.net>
 *
 * The TMC FPGA MFD core driver for Juniper hardware.
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


#include <linux/device.h>
#include <linux/module.h>
#include <linux/pci.h>
#include <linux/delay.h>
#include <linux/sched.h>
#include <linux/io.h>
#include <linux/interrupt.h>
#include <linux/of.h>
#include <linux/acpi.h>
#include <linux/irqdomain.h>
#include <linux/mfd/core.h>
#include "jnx-tmc.h"

#define TMC_DO_SCRATCH_TEST	1

#define PCI_VENDOR_ID_JUNIPER           0x1304
#define PCI_DEVICE_ID_JNX_TMC_CHD     0x007B
#define PCI_DEVICE_ID_JNX_TMC_PFE     0x007C
#define PCI_DEVICE_ID_JNX_XMC_CHD       0x00D8
#define PCI_DEVICE_ID_JNX_XMC_PFE       0x00D9
#define PCI_DEVICE_ID_TOMATIN_CHD       0x00EC
#define PCI_DEVICE_ID_TOMATIN_PFE       0x00ED

/*
 * TMC resources
 */
static struct resource tmc_resource_i2c[] = {
	/* I2C AUTOMATION Block */
	{
		.name  = "i2c-tmc",
		.start = TMC_I2C_AUTOMATION_I2C_CONTROL_START,
		.end   = TMC_I2C_AUTOMATION_I2C_CONTROL_END,
		.flags = IORESOURCE_MEM,
	},

	/* I2C DPMEM */
	{
		.name  = "i2c-tmc-mem",
		.start = TMC_I2C_DPMEM_ENTRY_START,
		.end   = TMC_I2C_DPMEM_ENTRY_END,
		.flags = IORESOURCE_MEM,
	},
};

#define TMC_RES_I2C_NR	ARRAY_SIZE(tmc_resource_i2c)

static struct resource tmc_resource_spi[] = {
	/* SPI Block */
	{
		.name  = "spi-tmc",
		.start = TMC_CHD_SPI_MASTER_SPI_CONTROL_START,
		.end   = TMC_CHD_SPI_MASTER_SPI_CONTROL_END,
		.flags = IORESOURCE_MEM,
	},

	/* SPI Mem Block */
	{
		.name  = "spi-tmc-mem",
		.start = TMC_CHD_SPI_MEM_MEM_SPI_MEM_START,
		.end   = TMC_CHD_SPI_MEM_MEM_SPI_MEM_END,
		.flags = IORESOURCE_MEM,
	},
};

#define TMC_RES_SPI_NR	ARRAY_SIZE(tmc_resource_spi)

/*
 * LED resources
 */
static struct resource tmc_resource_leds[] = {
	{
		.name  = "leds-tmc",
		.start = TMC_LED_CONTROL_START,
		.end   = TMC_LED_CONTROL_END,
		.flags = IORESOURCE_MEM,
	},
};

#define TMC_RES_LEDS_NR	ARRAY_SIZE(tmc_resource_leds)

/*
 * TMC RE-FPGA devices
 */
static struct resource tmc_resource_refpga[] = {
	{
		.name  = "refpga-tmc",
		.start = TMC_REFPGA_ACCESS_START,
		.end   = TMC_REFPGA_ACCESS_END,
		.flags = IORESOURCE_MEM,
	},
};

#define TMC_RES_REFPGA_NR  ARRAY_SIZE(tmc_resource_refpga)

static struct resource tmc_resource_gpioslave0[] = {
	/* SLAVE0 Block */
	{
		.name  = "gpioslave0-tmc",
		.start = TMC_GPIO_SLAVE0_START,
		.end   = TMC_GPIO_SLAVE0_END,
		.flags = IORESOURCE_MEM,
	}
};

#define TMC_RES_GPIOSLAVE0_NR	ARRAY_SIZE(tmc_resource_gpioslave0)

static struct resource tmc_resource_gpioslave1[] = {
	/* SLAVE1 Block */
	{
		.name  = "gpioslave1-tmc",
		.start = TMC_GPIO_SLAVE1_START,
		.end   = TMC_GPIO_SLAVE1_END,
		.flags = IORESOURCE_MEM,
	}
};

#define TMC_RES_GPIOSLAVE1_NR	ARRAY_SIZE(tmc_resource_gpioslave1)

static struct resource tmc_resource_gpioslave2[] = {
	/* SLAVE2 Block */
	{
		.name  = "gpioslave2-tmc",
		.start = TMC_GPIO_SLAVE2_START,
		.end   = TMC_GPIO_SLAVE2_END,
		.flags = IORESOURCE_MEM,
	}
};

#define TMC_RES_GPIOSLAVE2_NR	ARRAY_SIZE(tmc_resource_gpioslave2)

static struct resource tmc_resource_gpioslave3[] = {
	/* SLAVE3 Block */
	{
		.name  = "gpioslave3-tmc",
		.start = TMC_GPIO_SLAVE3_START,
		.end   = TMC_GPIO_SLAVE3_END,
		.flags = IORESOURCE_MEM,
	}
};

static struct resource tmc_resource_ptp_gpiocfg[] = {
	/* PTP CONFIG Block */
	{
		.name  = "ptpcfg-tmc",
		.start = TMC_GPIO_PTP_CFG_START,
		.end   = TMC_GPIO_PTP_CFG_END,
		.flags = IORESOURCE_MEM,
	}
};

static struct resource tmc_resource_ptp_gpioreset[] = {
	/* PTP CONFIG Block */
	{
		.name  = "ptpreset-tmc",
		.start = TMC_GPIO_PTP_RESET_START,
		.end   = TMC_GPIO_PTP_RESET_END,
		.flags = IORESOURCE_MEM,
	}
};

static struct resource tmc_resource_ptp_gpiodata[] = {
	/* PTP CONFIG Block */
	{
		.name  = "ptpdata-tmc",
		.start = TMC_GPIO_PTP_DATA_START,
		.end   = TMC_GPIO_PTP_DATA_END,
		.flags = IORESOURCE_MEM,
	}
};

#define TMC_RES_GPIOSLAVE3_NR	ARRAY_SIZE(tmc_resource_gpioslave3)

static struct resource tmc_resource_sfp_gpioslave0[] = {
	/* SFP SLAVE Block */
	{
		.name  = "gpioslave0-sfp-tmc",
		.start = TMC_GPIO_SFP_SLAVE0_START,
		.end   = TMC_GPIO_SFP_SLAVE0_END,
		.flags = IORESOURCE_MEM,
	}
};

#define TMC_RES_SFP_GPIOSLAVE0_NR	ARRAY_SIZE(tmc_resource_sfp_gpioslave0)

static struct resource tmc_resource_sfp_gpioslave1[] = {
	/* SFP SLAVE Block */
	{
		.name  = "gpioslave1-sfp-tmc",
		.start = TMC_GPIO_SFP_SLAVE1_START,
		.end   = TMC_GPIO_SFP_SLAVE1_END,
		.flags = IORESOURCE_MEM,
	}
};

#define TMC_RES_SFP_GPIOSLAVE1_NR	ARRAY_SIZE(tmc_resource_sfp_gpioslave1)

static struct resource tmc_resource_irq[] = {
	/* PSU Block */
	{
		.name  = "irq-tmc",
		.start = TMC_PSU_START,
		.end   = TMC_PSU_END,
		.flags = IORESOURCE_MEM,
	}
};

#define TMC_RES_IRQ_NR	ARRAY_SIZE(tmc_resource_irq)

static struct resource tmc_resource_fan[] = {
	/* PSU Block */
	{
		.name  = "fan-tmc",
		.start = TMC_FAN_START,
		.end   = TMC_FAN_END,
		.flags = IORESOURCE_MEM,
	}
};

#define TMC_RES_FAN_NR	ARRAY_SIZE(tmc_resource_fan)

static struct resource tmc_resource_ds100_mux[] = {
	/* PSU Block */
	{
		.name  = "irq-tmc",
		.start = TMC_GPIO_MUX_SLAVE_START,
		.end   = TMC_GPIO_MUX_SLAVE_END,
		.flags = IORESOURCE_MEM,
	}
};

#define TMC_RES_DS100_MUX_NR	ARRAY_SIZE(tmc_resource_ds100_mux)

static struct resource tmc_resource_ptp_clk_mux[] = {
	{
		.name  = "ptp-clk-mux-tmc",
		.start = TMC_GPIO_PTP_CLK_MUX_SLAVE_START,
		.end   = TMC_GPIO_PTP_CLK_MUX_SLAVE_END,
		.flags = IORESOURCE_MEM,
	}
};

#define TMC_RES_PTP_CLK_MUX_NR	ARRAY_SIZE(tmc_resource_ptp_clk_mux)

static struct resource xmc_resource_gpioslave0[] = {
	/* XMC SLAVE0 Block */
	{
		.name  = "gpioslave0-xmc",
		.start = XMC_GPIO_SLAVE0_START,
		.end   = XMC_GPIO_SLAVE0_END,
		.flags = IORESOURCE_MEM,
	}
};

#define XMC_RES_GPIOSLAVE0_NR	ARRAY_SIZE(xmc_resource_gpioslave0)

static struct resource xmc_resource_gpioslave1[] = {
	/* XMC SLAVE1 Block */
	{
		.name  = "gpioslave1-xmc",
		.start = XMC_GPIO_SLAVE1_START,
		.end   = XMC_GPIO_SLAVE1_END,
		.flags = IORESOURCE_MEM,
	}
};

#define XMC_RES_GPIOSLAVE1_NR	ARRAY_SIZE(xmc_resource_gpioslave1)

static struct resource xmc_resource_extdev_gpioreset[] = {
	/* EXT Device Reset Block */
	{
		.name  = "extdevreset-xmc",
		.start = XMC_GPIO_EXT_DEV_RESET_START,
		.end   = XMC_GPIO_EXT_DEV_RESET_END,
		.flags = IORESOURCE_MEM,
	}
};

static struct resource txmc_resource_gpioslave0[] = {
	/* TXMC SLAVE0 Block */
	{
		.name  = "gpioslave0-txmc",
		.start = TXMC_GPIO_SLAVE0_START,
		.end   = TXMC_GPIO_SLAVE0_END,
		.flags = IORESOURCE_MEM,
	}
};

#define TXMC_RES_GPIOSLAVE0_NR	ARRAY_SIZE(txmc_resource_gpioslave0)

static struct resource txmc_resource_gpioslave1[] = {
	/* TXMC SLAVE1 Block */
	{
		.name  = "gpioslave1-txmc",
		.start = TXMC_GPIO_SLAVE1_START,
		.end   = TXMC_GPIO_SLAVE1_END,
		.flags = IORESOURCE_MEM,
	}
};

#define TXMC_RES_GPIOSLAVE1_NR	ARRAY_SIZE(txmc_resource_gpioslave1)

static struct resource txmc_resource_gpioslave2[] = {
	/* TXMC SLAVE2 Block */
	{
		.name  = "gpioslave2-txmc",
		.start = TXMC_GPIO_SLAVE2_START,
		.end   = TXMC_GPIO_SLAVE2_END,
		.flags = IORESOURCE_MEM,
	}
};

#define TXMC_RES_GPIOSLAVE2_NR	ARRAY_SIZE(txmc_resource_gpioslave2)

static struct resource txmc_sfp_resource_gpioslave1[] = {
	/* TXMC SLAVE2 Block */
	{
		.name  = "gpioslave1-sfp-tmc",
		.start = TXMC_GPIO_SFP_SLAVE1_START,
		.end   = TXMC_GPIO_SFP_SLAVE1_END,
		.flags = IORESOURCE_MEM,
	}
};

#define TXMC_SFP_RES_GPIOSLAVE1_NR	ARRAY_SIZE(txmc_sfp_resource_gpioslave1)

static struct resource txmc_resource_extdev_gpioreset[] = {
	/* EXT Device Reset Block */
	{
		.name  = "extdevreset-txmc",
		.start = TXMC_GPIO_EXT_DEV_RESET_START,
		.end   = TXMC_GPIO_EXT_DEV_RESET_END,
		.flags = IORESOURCE_MEM,
	}
};

static struct resource tmc_resource_pri_clk_mux[] = {
	{
		.name  = "pri-clk-mux-tmc",
		.start = TMC_GPIO_PRI_CLK_MUX_START,
		.end   = TMC_GPIO_PRI_CLK_MUX_END,
		.flags = IORESOURCE_MEM,
	}
};

static struct resource tmc_resource_sec_clk_mux[] = {
	{
		.name  = "sec-clk-mux-tmc",
		.start = TMC_GPIO_SEC_CLK_MUX_START,
		.end   = TMC_GPIO_SEC_CLK_MUX_END,
		.flags = IORESOURCE_MEM,
	}
};

static struct resource tmc_resource_pll_status[] = {
	{
		.name  = "pll-status-tmc",
		.start = TMC_GPIO_PLL_STATUS_START,
		.end   = TMC_GPIO_PLL_STATUS_END,
		.flags = IORESOURCE_MEM,
	}
};

/*
 * CHASSISD TMC MFD devices
 */
static struct mfd_cell chassisd_tmc_mfd_devs[] = {
	{
		.name = "i2c-tmc",
		.num_resources = ARRAY_SIZE(tmc_resource_i2c),
		.resources = &tmc_resource_i2c[0],
		.of_compatible = "jnx,i2c-tmc",
		.id = 0,
	},
	{
		.name = "spi-tmc",
		.num_resources = ARRAY_SIZE(tmc_resource_spi),
		.resources = &tmc_resource_spi[0],
		.of_compatible = "jnx,spi-supercon",
		.id = 0,
	},
	{
		.name = "leds-tmc",
		.num_resources = ARRAY_SIZE(tmc_resource_leds),
		.resources = &tmc_resource_leds[0],
		.of_compatible = "jnx,leds-tmc",
		.id = 0,
	},
	{
		.name = "refpga-tmc",
		.num_resources = ARRAY_SIZE(tmc_resource_refpga),
		.resources = &tmc_resource_refpga[0],
		.of_compatible = "jnx,refpga-tmc",
		.id = 0,
	},
	{
		.name = "irq-tmc",
		.num_resources = ARRAY_SIZE(tmc_resource_irq),
		.resources = &tmc_resource_irq[0],
		.of_compatible = "jnx,irq-tmc",
		.id = 0,
	},
	{
		.name = "fan-tmc",
		.num_resources = ARRAY_SIZE(tmc_resource_fan),
		.resources = &tmc_resource_fan[0],
		.of_compatible = "jnx,fan-tmc",
		.id = 0,
	},
	{
		.name = "ds100-mux-tmc",
		.num_resources = ARRAY_SIZE(tmc_resource_ds100_mux),
		.resources = &tmc_resource_ds100_mux[0],
		.of_compatible = "jnx,ds100-mux-tmc",
		.id = 0,
	},
	{
		.name = "ptp-clk-mux-tmc",
		.num_resources = ARRAY_SIZE(tmc_resource_ptp_clk_mux),
		.resources = &tmc_resource_ptp_clk_mux[0],
		.of_compatible = "jnx,ptp-clk-mux-tmc",
		.id = 0,
	},
	{
		.name = "ptpcfg-tmc",
		.num_resources = ARRAY_SIZE(tmc_resource_ptp_gpiocfg),
		.resources = &tmc_resource_ptp_gpiocfg[0],
		.of_compatible = "jnx,ptpcfg-tmc",
		.id = 0,
	},
	{
		.name = "ptpreset-tmc",
		.num_resources = ARRAY_SIZE(tmc_resource_ptp_gpioreset),
		.resources = &tmc_resource_ptp_gpioreset[0],
		.of_compatible = "jnx,ptpreset-tmc",
		.id = 0,
	},
	{
		.name = "ptpdata-tmc",
		.num_resources = ARRAY_SIZE(tmc_resource_ptp_gpiodata),
		.resources = &tmc_resource_ptp_gpiodata[0],
		.of_compatible = "jnx,ptpdata-tmc",
		.id = 0,
	},
	{
		.name = "pri-clk-mux-tmc",
		.num_resources = ARRAY_SIZE(tmc_resource_pri_clk_mux),
		.resources = &tmc_resource_pri_clk_mux[0],
		.of_compatible = "jnx,clk-mux-tmc",
		.id = 0,
	},
	{
		.name = "sec-clk-mux-tmc",
		.num_resources = ARRAY_SIZE(tmc_resource_pri_clk_mux),
		.resources = &tmc_resource_sec_clk_mux[0],
		.of_compatible = "jnx,clk-mux-tmc",
		.id = 0,
	},
	{
		.name = "pll-status-tmc",
		.num_resources = ARRAY_SIZE(tmc_resource_pll_status),
		.resources = &tmc_resource_pll_status[0],
		.of_compatible = "jnx,pll-status-tmc",
		.id = 0,
	},
};

/*
 * PFE TMC MFD devices
 */
static struct mfd_cell pfe_tmc_mfd_devs[] = {
	{
		.name = "i2c-tmc",
		.num_resources = ARRAY_SIZE(tmc_resource_i2c),
		.resources = &tmc_resource_i2c[0],
		.of_compatible = "jnx,i2c-tmc",
		.id = 0,
	},
	{
		.name = "gpioslave0-tmc",
		.num_resources = ARRAY_SIZE(tmc_resource_gpioslave0),
		.resources = &tmc_resource_gpioslave0[0],
		.of_compatible = "jnx,gpioslave0-tmc",
		.id = 0,
	},
	{
		.name = "gpioslave1-tmc",
		.num_resources = ARRAY_SIZE(tmc_resource_gpioslave1),
		.resources = &tmc_resource_gpioslave1[0],
		.of_compatible = "jnx,gpioslave1-tmc",
		.id = 0,
	},
	{
		.name = "gpioslave2-tmc",
		.num_resources = ARRAY_SIZE(tmc_resource_gpioslave2),
		.resources = &tmc_resource_gpioslave2[0],
		.of_compatible = "jnx,gpioslave2-tmc",
		.id = 0,
	},
	{
		.name = "gpioslave3-tmc",
		.num_resources = ARRAY_SIZE(tmc_resource_gpioslave3),
		.resources = &tmc_resource_gpioslave3[0],
		.of_compatible = "jnx,gpioslave3-tmc",
		.id = 0,
	},
	{
		.name = "gpioslave0-sfp-tmc",
		.num_resources = ARRAY_SIZE(tmc_resource_sfp_gpioslave0),
		.resources = &tmc_resource_sfp_gpioslave0[0],
		.of_compatible = "jnx,gpioslave0-sfp-tmc",
		.id = 0,
	},
	{
		.name = "gpioslave1-sfp-tmc",
		.num_resources = ARRAY_SIZE(tmc_resource_sfp_gpioslave1),
		.resources = &tmc_resource_sfp_gpioslave1[0],
		.of_compatible = "jnx,gpioslave1-sfp-tmc",
		.id = 0,
	},
};

/*
 * PFE XMC MFD devices
 */
static struct mfd_cell pfe_xmc_mfd_devs[] = {
	{
		.name = "i2c-tmc",
		.num_resources = ARRAY_SIZE(tmc_resource_i2c),
		.resources = &tmc_resource_i2c[0],
		.of_compatible = "jnx,i2c-tmc",
		.id = 0,
	},
	{
		.name = "extdevreset-xmc",
		.num_resources = ARRAY_SIZE(xmc_resource_extdev_gpioreset),
		.resources = &xmc_resource_extdev_gpioreset[0],
		.of_compatible = "jnx,extdevreset-xmc",
		.id = 0,
	},
	{
		.name = "gpioslave0-xmc",
		.num_resources = ARRAY_SIZE(xmc_resource_gpioslave0),
		.resources = &xmc_resource_gpioslave0[0],
		.of_compatible = "jnx,gpioslave0-xmc",
		.id = 0,
	},
	{
		.name = "gpioslave1-xmc",
		.num_resources = ARRAY_SIZE(xmc_resource_gpioslave1),
		.resources = &xmc_resource_gpioslave1[0],
		.of_compatible = "jnx,gpioslave1-xmc",
		.id = 0,
	},
};

/*
 * PFE TXMC MFD devices
 */
static struct mfd_cell pfe_txmc_mfd_devs[] = {
	{
		.name = "i2c-tmc",
		.num_resources = ARRAY_SIZE(tmc_resource_i2c),
		.resources = &tmc_resource_i2c[0],
		.of_compatible = "jnx,i2c-tmc",
		.id = 0,
	},
	{
		.name = "extdevreset-txmc",
		.num_resources = ARRAY_SIZE(txmc_resource_extdev_gpioreset),
		.resources = &txmc_resource_extdev_gpioreset[0],
		.of_compatible = "jnx,extdevreset-txmc",
		.id = 0,
	},
	{
		.name = "gpioslave0-txmc",
		.num_resources = ARRAY_SIZE(txmc_resource_gpioslave0),
		.resources = &txmc_resource_gpioslave0[0],
		.of_compatible = "jnx,gpioslave0-txmc",
		.id = 0,
	},
	{
		.name = "gpioslave1-txmc",
		.num_resources = ARRAY_SIZE(txmc_resource_gpioslave1),
		.resources = &txmc_resource_gpioslave1[0],
		.of_compatible = "jnx,gpioslave1-txmc",
		.id = 0,
	},
	{
		.name = "gpioslave2-txmc",
		.num_resources = ARRAY_SIZE(txmc_resource_gpioslave2),
		.resources = &txmc_resource_gpioslave2[0],
		.of_compatible = "jnx,gpioslave2-txmc",
		.id = 0,
	},
	{
		.name = "gpioslave1-sfp-txmc",
		.num_resources = ARRAY_SIZE(txmc_sfp_resource_gpioslave1),
		.resources = &txmc_sfp_resource_gpioslave1[0],
		.of_compatible = "jnx,gpioslave1-sfp-txmc",
		.id = 0,
	},
};

struct tmc_optic_cpld_version {
	u32 optic_cpld_major; /* optic cpld major version */
	u32 optic_cpld_minor; /* optic cpld minor version */
	u32 optic_cpld_devid; /* optic cpld device id */
};

struct tmc_fpga_data {
	void __iomem *membase;
	struct pci_dev *pdev;

	u32 major;   /* Device id & Major version*/
	u32 minor;	/* Minor version */

	struct tmc_optic_cpld_version ocpld[OPTIC_CPLDS_MAX];
	u32 pm_poweroff_unsupported; /* poweroff not support */
};

/* Default platform pm_power_off handler */
static void (*default_pm_power_off)(void);
/* TMC device registered for the power off */
static struct tmc_fpga_data *tmc_power_off_data;

/* sysfs entries */
static ssize_t major_show(struct device *dev, struct device_attribute *attr,
			    char *buf)
{
	struct tmc_fpga_data *tmc = dev_get_drvdata(dev);

	return sprintf(buf, "0x%02X_%06X\n",
		       (tmc->major >> 24) & 0xff,
		       tmc->major & 0xffffff);
}

static ssize_t minor_show(struct device *dev, struct device_attribute *attr,
			   char *buf)
{
	struct tmc_fpga_data *tmc = dev_get_drvdata(dev);

	return sprintf(buf, "%02X\n", (tmc->minor) & 0xff);
}

static ssize_t optic_cpld_major_show(struct device *dev,
				struct device_attribute *attr, char *buf)
{
	struct tmc_fpga_data *tmc = dev_get_drvdata(dev);

	return sprintf(buf, "%01X\n", tmc->ocpld[0].optic_cpld_major & 0xf);
}

static ssize_t optic_cpld_devid_show(struct device *dev,
				struct device_attribute *attr, char *buf)
{
	struct tmc_fpga_data *tmc = dev_get_drvdata(dev);

	return sprintf(buf, "%01X\n",
		       (tmc->ocpld[0].optic_cpld_major >> 4) & 0xf);
}

static ssize_t optic_cpld_minor_show(struct device *dev,
				struct device_attribute *attr, char *buf)
{
	struct tmc_fpga_data *tmc = dev_get_drvdata(dev);

	return sprintf(buf, "%02X\n", tmc->ocpld[0].optic_cpld_minor & 0xff);
}

static ssize_t optic_cpld1_major_show(struct device *dev,
				      struct device_attribute *attr, char *buf)
{
	struct tmc_fpga_data *tmc = dev_get_drvdata(dev);

	return sprintf(buf, "%01X\n", tmc->ocpld[1].optic_cpld_major & 0xf);
}

static ssize_t optic_cpld1_devid_show(struct device *dev,
				      struct device_attribute *attr, char *buf)
{
	struct tmc_fpga_data *tmc = dev_get_drvdata(dev);

	return sprintf(buf, "%01X\n",
		       (tmc->ocpld[1].optic_cpld_major >> 4) & 0xf);
}

static ssize_t optic_cpld1_minor_show(struct device *dev,
				      struct device_attribute *attr, char *buf)
{
	struct tmc_fpga_data *tmc = dev_get_drvdata(dev);

	return sprintf(buf, "%02X\n", tmc->ocpld[1].optic_cpld_minor & 0xff);
}

static ssize_t optic_cpld2_major_show(struct device *dev,
				      struct device_attribute *attr, char *buf)
{
	struct tmc_fpga_data *tmc = dev_get_drvdata(dev);

	return sprintf(buf, "%01X\n", tmc->ocpld[2].optic_cpld_major & 0xf);
}

static ssize_t optic_cpld2_devid_show(struct device *dev,
				      struct device_attribute *attr, char *buf)
{
	struct tmc_fpga_data *tmc = dev_get_drvdata(dev);

	return sprintf(buf, "%01X\n",
		       (tmc->ocpld[2].optic_cpld_major >> 4) & 0xf);
}

static ssize_t optic_cpld2_minor_show(struct device *dev,
				      struct device_attribute *attr, char *buf)
{
	struct tmc_fpga_data *tmc = dev_get_drvdata(dev);

	return sprintf(buf, "%02X\n", tmc->ocpld[2].optic_cpld_minor & 0xff);
}

static ssize_t set_sys_shutdown(struct device *dev,
				struct device_attribute *devattr,
				const char *buf,
				size_t len)
{

	struct tmc_fpga_data *tmc = dev_get_drvdata(dev);
	unsigned long val;
	int ret;

	ret = kstrtoul(buf, 0, &val);
	if (ret < 0)
		return ret;

	if (val != 1)
		return -EINVAL;

	/* Unlock the shutdown register */
	iowrite32(0x12345678, tmc->membase + TMC_SYS_SHUTDOWN_LOCK);
	iowrite32(0x1, tmc->membase + TMC_SYS_SHUTDOWN);

	return len;
}


static DEVICE_ATTR(major, S_IRUGO, major_show, NULL);
static DEVICE_ATTR(minor, S_IRUGO, minor_show, NULL);
static DEVICE_ATTR(optic_cpld_major, S_IRUGO, optic_cpld_major_show, NULL);
static DEVICE_ATTR(optic_cpld_devid, S_IRUGO, optic_cpld_devid_show, NULL);
static DEVICE_ATTR(optic_cpld_minor, S_IRUGO, optic_cpld_minor_show, NULL);
static DEVICE_ATTR(optic_cpld1_major, S_IRUGO, optic_cpld1_major_show, NULL);
static DEVICE_ATTR(optic_cpld1_devid, S_IRUGO, optic_cpld1_devid_show, NULL);
static DEVICE_ATTR(optic_cpld1_minor, S_IRUGO, optic_cpld1_minor_show, NULL);
static DEVICE_ATTR(optic_cpld2_major, S_IRUGO, optic_cpld2_major_show, NULL);
static DEVICE_ATTR(optic_cpld2_devid, S_IRUGO, optic_cpld2_devid_show, NULL);
static DEVICE_ATTR(optic_cpld2_minor, S_IRUGO, optic_cpld2_minor_show, NULL);
static DEVICE_ATTR(shutdown, S_IWUSR, NULL, set_sys_shutdown);

static struct attribute *tmc_attrs[] = {
	&dev_attr_major.attr,
	&dev_attr_minor.attr,
	&dev_attr_optic_cpld_major.attr,
	&dev_attr_optic_cpld_devid.attr,
	&dev_attr_optic_cpld_minor.attr,
	&dev_attr_optic_cpld1_major.attr,
	&dev_attr_optic_cpld1_devid.attr,
	&dev_attr_optic_cpld1_minor.attr,
	&dev_attr_optic_cpld2_major.attr,
	&dev_attr_optic_cpld2_devid.attr,
	&dev_attr_optic_cpld2_minor.attr,
	&dev_attr_shutdown.attr,
	NULL,
};

static struct attribute_group tmc_attr_group = {
	.attrs  = tmc_attrs,
};

#if defined TMC_DO_SCRATCH_TEST
/* Do a quick scratch access test */
static int tmc_do_test_scratch(struct tmc_fpga_data *tmc)
{
	struct pci_dev *pdev = tmc->pdev;
	struct device *dev = &pdev->dev;
	int offset = TMC_SCRATCH;
	u32 acc, val = 0xdeadbeaf;

	/*
	 * Check rw register access -> use the scratch reg.
	 */
	iowrite32(val, tmc->membase + offset);
	acc = ioread32(tmc->membase + offset);
	if (acc != val) {
		dev_err(dev, "Tmc scratch(0x%x) failed: %08x.%08x!\n",
			offset, val, acc);
		return -EIO;
	}

	for (val = 0; val < 0xf0000000; val += 0x01010101) {
		iowrite32(val, tmc->membase + offset);
		acc = ioread32(tmc->membase + offset);
		if (acc != val) {
			dev_err(dev, "Tmc scratch(0x%x) failed: %08x.%08x!\n",
				offset, val, acc);
			return -EIO;
		}
	}

	/*
	 * Write a sig before leaving..
	 */
	val = 0xcafebabe;
	iowrite32(val, tmc->membase + offset);
	dev_dbg(dev, "Tmc scratch result: 0x%08x\n",
		 ioread32(tmc->membase + offset));

	return 0;
}
#endif /* TMC_DO_SCRATCH_TEST */

/* tmc_fpga_power_off
 * pm_power_off handler using the TMC CHD on Nautilus.
 */
static void tmc_fpga_power_off(void)
{
	struct tmc_fpga_data *tmc = tmc_power_off_data;

	/* Unlock the shutdown register */
	iowrite32(0x12345678, tmc->membase + TMC_SYS_SHUTDOWN_LOCK);
	/* Request shutdown */
	iowrite32(0x1, tmc->membase + TMC_SYS_SHUTDOWN);
}

static int tmc_fpga_probe(struct pci_dev *pdev,
			       const struct pci_device_id *id)
{
	int err;
	struct tmc_fpga_data *tmc;
	struct device *dev = &pdev->dev;

	dev_dbg(dev, "Tmc FPGA Probe called\n");

	tmc = devm_kzalloc(dev, sizeof(*tmc), GFP_KERNEL);
	if (!tmc)
		return -ENOMEM;

	err = pcim_enable_device(pdev);
	if (err) {
		dev_err(&pdev->dev, "Failed to enable device %d\n", err);
		return err;
	}

	err = pcim_iomap_regions(pdev, 1 << 0, "tmc-core");
	if (err) {
		dev_err(&pdev->dev, "Failed to iomap regions %d\n", err);
		goto err_disable;
	}

	tmc->membase = pcim_iomap_table(pdev)[0];
	if (IS_ERR(tmc->membase)) {
		dev_err(dev, "pci_ioremap_bar() failed\n");
		err = -ENOMEM;
		goto err_release;
	}

	tmc->pdev = pdev;
	pci_set_drvdata(pdev, tmc);

	/* All Tmc uses MSI interrupts - enable bus mastering */
	pci_set_master(pdev);

	/* Disable ACPI processing of child nodes if they aren't set
	 * properly by the Bios.
	 */
	if (ACPI_COMPANION(dev)) {
		switch (pdev->device) {
		case PCI_DEVICE_ID_TOMATIN_CHD:
		case PCI_DEVICE_ID_TOMATIN_PFE:
			ACPI_COMPANION_SET(dev, NULL);
			break;
		default:
			break;
		}
	}

#if defined TMC_DO_SCRATCH_TEST
	/* Check IO before proceeding */
	dev_dbg(dev, "Tmc FPGA starting scratch test\n");
	err = tmc_do_test_scratch(tmc);
	if (err)
		goto err_unmap;

	dev_dbg(dev, "Tmc FPGA scratch test passed !!!\n");
#endif /* TMC_DO_SCRATCH_TEST */

	switch (id->device) {
	case PCI_DEVICE_ID_JNX_TMC_CHD:
	case PCI_DEVICE_ID_TOMATIN_CHD:
	case PCI_DEVICE_ID_JNX_XMC_CHD:
		err = mfd_add_devices(dev, pdev->bus->number,
				&chassisd_tmc_mfd_devs[0],
				ARRAY_SIZE(chassisd_tmc_mfd_devs),
				&pdev->resource[0],
				0, NULL /* tmc->irq_domain */);
		break;
	case PCI_DEVICE_ID_JNX_TMC_PFE:
		err = mfd_add_devices(dev, pdev->bus->number,
					&pfe_tmc_mfd_devs[0],
					ARRAY_SIZE(pfe_tmc_mfd_devs),
					&pdev->resource[0],
					0, NULL /* tmc->irq_domain */);
		break;
	case PCI_DEVICE_ID_JNX_XMC_PFE:
		err = mfd_add_devices(dev, pdev->bus->number,
				      &pfe_xmc_mfd_devs[0],
				      ARRAY_SIZE(pfe_xmc_mfd_devs),
				      &pdev->resource[0],
				      0, NULL /* tmc->irq_domain */);
		break;
	case PCI_DEVICE_ID_TOMATIN_PFE:
		err = mfd_add_devices(dev, pdev->bus->number,
				      &pfe_txmc_mfd_devs[0],
				      ARRAY_SIZE(pfe_txmc_mfd_devs),
				      &pdev->resource[0],
				      0, NULL /* tmc->irq_domain */);
		break;
	default:
		dev_err(&pdev->dev, "Invalid PCI Device ID id:%d\n",
				id->device);
		goto err_unmap;
	}

	if (err < 0) {
		dev_err(&pdev->dev, "Failed to add mfd devices %d\n", err);
		goto err_unmap;
	}

	err = sysfs_create_group(&pdev->dev.kobj, &tmc_attr_group);
	if (err) {
		sysfs_remove_group(&pdev->dev.kobj, &tmc_attr_group);
		dev_err(&pdev->dev, "Failed to create attr group\n");
		goto err_remove_mfd;
	}

	tmc->major = ioread32(tmc->membase + TMC_REVISION);
	tmc->minor = ioread32(tmc->membase + TMC_MINOR);

	tmc->ocpld[0].optic_cpld_major = ioread32(tmc->membase
						  + TMC_OPTIC_CPLD_MAJOR);
	tmc->ocpld[0].optic_cpld_minor = ioread32(tmc->membase
						  + TMC_OPTIC_CPLD_MINOR);

	dev_info(dev, "Tmc FPGA Revision: 0x%02X_%06X, Minor: %02X\n",
		 (tmc->major >> 24) & 0xff,
		 tmc->major & 0xffffff,
		 (tmc->minor) & 0xff);
	dev_info(dev,
		 "Tmc FPGA optic cpld Major: 0x%01X, Minor: 0x%02X Devid: 0x%01X\n",
		 (tmc->ocpld[0].optic_cpld_major) & 0xf,
		 (tmc->ocpld[0].optic_cpld_minor) & 0xff,
		 (tmc->ocpld[0].optic_cpld_major >> 4) & 0xf);
	dev_info(dev, "Tmc FPGA mem:0x%lx\n",
		 (unsigned long)tmc->membase);

	/* Read Slave CPLD1 versions for XMC. */
	if (pdev->device == PCI_DEVICE_ID_JNX_XMC_PFE ||
        pdev->device == PCI_DEVICE_ID_TOMATIN_PFE) {
		tmc->ocpld[1].optic_cpld_major =
			ioread32(tmc->membase + XMC_OPTIC_CPLD1_MAJOR);
		tmc->ocpld[1].optic_cpld_minor =
			ioread32(tmc->membase + XMC_OPTIC_CPLD1_MINOR);

		dev_info(dev,
			 "XMC FPGA optic cpld1 Major: 0x%01X, Minor: 0x%02X Devid: 0x%01X\n",
			 (tmc->ocpld[1].optic_cpld_major) & 0xf,
			 (tmc->ocpld[1].optic_cpld_minor) & 0xff,
			 (tmc->ocpld[1].optic_cpld_major >> 4) & 0xf);
	}

	/* Read Slave CPLD2 versions for TXMC. */
	if (pdev->device == PCI_DEVICE_ID_TOMATIN_PFE) {
		tmc->ocpld[2].optic_cpld_major =
			ioread32(tmc->membase + TXMC_OPTIC_CPLD2_MAJOR);
		tmc->ocpld[2].optic_cpld_minor =
			ioread32(tmc->membase + TXMC_OPTIC_CPLD2_MINOR);

		dev_info(dev,
			 "TXMC FPGA optic cpld2 Major: 0x%01X, Minor: 0x%02X Devid: 0x%01X\n",
			 (tmc->ocpld[2].optic_cpld_major) & 0xf,
			 (tmc->ocpld[2].optic_cpld_minor) & 0xff,
			 (tmc->ocpld[2].optic_cpld_major >> 4) & 0xf);
	}

		/* Finalize the data from Device Tree if present */
		if (dev->of_node) {
			of_property_read_u32(dev->of_node,
			    "pm_poweroff_unsupported",
			    &tmc->pm_poweroff_unsupported);
		}

	/* Install the TMC CHD pm_power_off handler */
	if (pdev->device == PCI_DEVICE_ID_JNX_TMC_CHD ||
        pdev->device == PCI_DEVICE_ID_TOMATIN_CHD ||
	    pdev->device == PCI_DEVICE_ID_JNX_XMC_CHD) {
		dev_info(dev, "Replacing pm_power_off (%p)\n",
			 pm_power_off);
		if (!tmc->pm_poweroff_unsupported) {
			tmc_power_off_data = tmc;
			default_pm_power_off = pm_power_off;
			pm_power_off = tmc_fpga_power_off;
		}
	}

	return 0;

err_remove_mfd:
	mfd_remove_devices(dev);
err_unmap:
	pci_iounmap(pdev, tmc->membase);
err_release:
	pci_release_regions(pdev);
err_disable:
	pci_disable_device(pdev);

	return err;
}

static void tmc_fpga_remove(struct pci_dev *pdev)
{
	struct tmc_fpga_data *tmc = dev_get_drvdata(&pdev->dev);

	sysfs_remove_group(&pdev->dev.kobj, &tmc_attr_group);
	mfd_remove_devices(&pdev->dev);
	if (pdev->device == PCI_DEVICE_ID_JNX_TMC_CHD ||
        pdev->device == PCI_DEVICE_ID_TOMATIN_CHD ||
	    pdev->device == PCI_DEVICE_ID_JNX_XMC_CHD) {
		if (!tmc->pm_poweroff_unsupported)
			pm_power_off = default_pm_power_off;
	}
}

static const struct pci_device_id tmc_fpga_id_tbl[] = {
	{ PCI_DEVICE(PCI_VENDOR_ID_JUNIPER, PCI_DEVICE_ID_JNX_TMC_CHD) },
	{ PCI_DEVICE(PCI_VENDOR_ID_JUNIPER, PCI_DEVICE_ID_JNX_TMC_PFE) },
	{ PCI_DEVICE(PCI_VENDOR_ID_JUNIPER, PCI_DEVICE_ID_JNX_XMC_CHD) },
	{ PCI_DEVICE(PCI_VENDOR_ID_JUNIPER, PCI_DEVICE_ID_JNX_XMC_PFE) },
	{ PCI_DEVICE(PCI_VENDOR_ID_JUNIPER, PCI_DEVICE_ID_TOMATIN_CHD) },
	{ PCI_DEVICE(PCI_VENDOR_ID_JUNIPER, PCI_DEVICE_ID_TOMATIN_PFE) },
	{ }
};
MODULE_DEVICE_TABLE(pci, tmc_fpga_id_tbl);

static struct pci_driver tmc_fpga_driver = {
	.name		= "tmc-core",
	.id_table	= tmc_fpga_id_tbl,
	.probe		= tmc_fpga_probe,
	.remove		= tmc_fpga_remove,
};

module_pci_driver(tmc_fpga_driver);

MODULE_DESCRIPTION("Juniper TMC FPGA MFD core driver");
MODULE_AUTHOR("Ashish Bhensdadia <bashish@juniper.net>");
MODULE_LICENSE("GPL");
