/*
 * Juniper GARNET MFD Core driver
 *
 * drivers/mfd/jnx-garnet-core.c
 *
 * This driver is being adpoted from supercon FPGA driver.
 *
 * Copyright (c) 2023, Juniper Networks
 * Author: Arun kumar Alapati (arunkumara@juniper.net)
 *
 * The Garnet FPGA MFD core driver for Accton hardware.
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
#include <linux/delay.h>
#include <linux/pci.h>
#include <linux/acpi.h>
#include <linux/delay.h>
#include <linux/sched.h>
#include <linux/io.h>
#include <linux/interrupt.h>
#include <linux/of.h>
#include <linux/irqdomain.h>
#include <linux/mfd/core.h>
#ifdef QFX_SONIC
#include <linux/jnx/pci_ids.h>
#endif
#include "qfx5241-jnx-garnet.h"
#include "qfx5241-jnx-garnet64-core.h"
#include "qfx5241-jnx-garnet32-core.h"
#include "qfx5241_i2c_mfd_cells.h"

#define GARNET_DO_SCRATCH_TEST  1
#define PCI_VENDOR_ID_ACCTON            0x10ee
#define PCI_DEVICE_ID_GARNET        0x7021
#define PCI_DEVICE_ID_GARNET32      0x7022

struct cpld_access_reg {
        uint32_t reg;
        bool is_valid;
};

static struct cpld_access_reg sysfs_cpld1_access;
static struct cpld_access_reg sysfs_cpld2_access;

/* sysfs entries */
static ssize_t major_show(struct device *dev, struct device_attribute *attr,
                                char *buf)
{
        struct garnet_fpga_data *garnet = dev_get_drvdata(dev);

        return sprintf(buf, "0x%02X_%06X\n",
                        (garnet->major >> 24) & 0xff,
                        garnet->major & 0xffffff);
}

static ssize_t minor_show(struct device *dev, struct device_attribute *attr,
                           char *buf)
{
        struct garnet_fpga_data *garnet = dev_get_drvdata(dev);

        return sprintf(buf, "%02X\n", (garnet->minor) & 0xff);
}

static ssize_t optic_cpld_major_show(struct device *dev,
                                struct device_attribute *attr, char *buf)
{
        struct garnet_fpga_data *garnet = dev_get_drvdata(dev);

        return sprintf(buf, "%02X\n", garnet->ocpld[0].optic_cpld_major & 0xff);
}

static ssize_t optic_cpld_devid_show(struct device *dev,
                                struct device_attribute *attr, char *buf)
{
        struct garnet_fpga_data *garnet = dev_get_drvdata(dev);

        return sprintf(buf, "%01X\n",
                        (garnet->ocpld[0].optic_cpld_major >> 4) & 0xf);
}

static ssize_t optic_cpld_minor_show(struct device *dev,
                                struct device_attribute *attr, char *buf)
{
        struct garnet_fpga_data *garnet = dev_get_drvdata(dev);

        return sprintf(buf, "%02X\n", garnet->ocpld[0].optic_cpld_minor & 0xff);
}

static ssize_t optic_cpld1_major_show(struct device *dev,
                struct device_attribute *attr, char *buf)
{
        struct garnet_fpga_data *garnet = dev_get_drvdata(dev);

        return sprintf(buf, "%02X\n", garnet->ocpld[1].optic_cpld_major & 0xff);
}

static ssize_t optic_cpld1_devid_show(struct device *dev,
                struct device_attribute *attr, char *buf)
{
        struct garnet_fpga_data *garnet = dev_get_drvdata(dev);

        return sprintf(buf, "%01X\n",
                        (garnet->ocpld[1].optic_cpld_major >> 4) & 0xf);
}

static ssize_t optic_cpld1_minor_show(struct device *dev,
                struct device_attribute *attr, char *buf)
{
        struct garnet_fpga_data *garnet = dev_get_drvdata(dev);

        return sprintf(buf, "%02X\n", garnet->ocpld[1].optic_cpld_minor & 0xff);
}

static ssize_t optic_cpld1_read(struct device *dev,
                struct device_attribute *attr, char *buf)
{
        uint32_t val;
        uint32_t reg = 0;
        uint32_t spi_busy_bit;
        struct garnet_fpga_data *garnet = dev_get_drvdata(dev);

        if (!garnet) {
                dev_err(dev, "Invalid driver data\n");
                sysfs_cpld1_access.is_valid = false;
                return EINVAL;
        }

        spi_busy_bit = 0;
        reg = sysfs_cpld1_access.reg + GARNET_CPLD1_BASE;

        if (sysfs_cpld1_access.is_valid && reg <= GARNET_CPLD1_END) {
                mutex_lock(&garnet->lock[spi_busy_bit]);
                CHECK_SPI_BUSY(garnet, spi_busy_bit);
                val = ioread8(garnet->cpld1_membase + reg);
                CHECK_SPI_BUSY(garnet, spi_busy_bit);
                mutex_unlock(&garnet->lock[spi_busy_bit]);
        } else {
                dev_err(dev, "CPLD register details are not valid\n");
                return EINVAL;
        }

        return sprintf(buf, "%02X\n", val);
}

static ssize_t optic_cpld1_store(struct device *dev,
                                struct device_attribute *devattr,
                                const char *buf,
                                size_t len)
{
        uint32_t val = 0;
        uint32_t reg = 0;
        uint32_t spi_busy_bit;
        struct garnet_fpga_data *garnet = dev_get_drvdata(dev);

        if (!garnet) {
                dev_err(dev, "Invalid driver data\n");
                sysfs_cpld1_access.is_valid = false;
                return EINVAL;
        }

        if(sscanf(buf, "set_reg 0x%04x", &reg) == 1) {
                if((reg + GARNET_CPLD1_BASE) <= GARNET_CPLD1_END) {
                        sysfs_cpld1_access.is_valid = true;
                        sysfs_cpld1_access.reg = reg;
                } else {
                        sysfs_cpld1_access.reg = 0x00;
                        sysfs_cpld1_access.is_valid = false;
                }
        } else if (sscanf(buf, "0x%x 0x%x", &reg, &val) == 2) {
                if ((reg + GARNET_CPLD1_BASE) <= GARNET_CPLD1_END) {
                        spi_busy_bit = 0;
                        reg = reg + GARNET_CPLD1_BASE;

                        mutex_lock(&garnet->lock[spi_busy_bit]);
                        CHECK_SPI_BUSY(garnet, spi_busy_bit);
                        iowrite8(val, garnet->cpld1_membase + reg);
                        CHECK_SPI_BUSY(garnet, spi_busy_bit);
                        mutex_unlock(&garnet->lock[spi_busy_bit]);
                }
        } else {
                sysfs_cpld1_access.is_valid = false;
                return EINVAL;
        }

        return len;
}

static ssize_t optic_cpld2_read(struct device *dev,
                struct device_attribute *attr, char *buf)
{
        uint8_t val;
        uint32_t reg = 0;
        uint32_t spi_busy_bit;
        struct garnet_fpga_data *garnet = dev_get_drvdata(dev);

        if (!garnet) {
                dev_err(dev, "Invalid driver data\n");
                sysfs_cpld2_access.is_valid = false;
                return EINVAL;
        }

        spi_busy_bit = 1;
        reg = sysfs_cpld2_access.reg + GARNET_CPLD2_BASE;

        if (sysfs_cpld2_access.is_valid && reg <= GARNET_CPLD2_END) {
                mutex_lock(&garnet->lock[spi_busy_bit]);
                CHECK_SPI_BUSY(garnet, spi_busy_bit);
                val = ioread8(garnet->cpld2_membase + reg);
                CHECK_SPI_BUSY(garnet, spi_busy_bit);
                mutex_unlock(&garnet->lock[spi_busy_bit]);
        } else {
                dev_err(dev, "CPLD register details are not valid\n");
                return EINVAL;
        }

        return sprintf(buf, "%02X\n", val);
}

static ssize_t optic_cpld2_store(struct device *dev,
                                struct device_attribute *devattr,
                                const char *buf,
                                size_t len)
{
        uint32_t val = 0;
        uint32_t reg = 0;
        uint32_t spi_busy_bit;
        struct garnet_fpga_data *garnet = dev_get_drvdata(dev);

        if (!garnet) {
                dev_err(dev, "Invalid driver data\n");
                sysfs_cpld2_access.is_valid = false;
                return EINVAL;
        }

        if(sscanf(buf, "set_reg 0x%04x", &reg) == 1) {
                if((reg + GARNET_CPLD2_BASE) <= GARNET_CPLD2_END) {
                        sysfs_cpld2_access.is_valid = true;
                        sysfs_cpld2_access.reg = reg;
                } else {
                        sysfs_cpld2_access.reg = 0x00;
                        sysfs_cpld2_access.is_valid = false;
                }
        } else if (sscanf(buf, "0x%x 0x%x", &reg, &val) == 2) {
                if((reg + GARNET_CPLD2_BASE) <= GARNET_CPLD2_END) {
                        spi_busy_bit = 1;
                        reg = reg + GARNET_CPLD2_BASE;

                        mutex_lock(&garnet->lock[spi_busy_bit]);
                        CHECK_SPI_BUSY(garnet, spi_busy_bit);
                        iowrite8(val, garnet->cpld2_membase + reg);
                        CHECK_SPI_BUSY(garnet, spi_busy_bit);
                        mutex_unlock(&garnet->lock[spi_busy_bit]);
                }
        } else {
                sysfs_cpld2_access.is_valid = false;
                return EINVAL;
        }

        return len;
}
static DEVICE_ATTR_RO(major);
static DEVICE_ATTR_RO(minor);
static DEVICE_ATTR_RO(optic_cpld_major);
static DEVICE_ATTR_RO(optic_cpld_devid);
static DEVICE_ATTR_RO(optic_cpld_minor);
static DEVICE_ATTR_RO(optic_cpld1_major);
static DEVICE_ATTR_RO(optic_cpld1_devid);
static DEVICE_ATTR_RO(optic_cpld1_minor);
static DEVICE_ATTR(optic_cpld1_access, S_IRUSR | S_IWUSR,
                        optic_cpld1_read, optic_cpld1_store);
static DEVICE_ATTR(optic_cpld2_access, S_IRUSR | S_IWUSR,
                        optic_cpld2_read, optic_cpld2_store);

static struct attribute *garnet_attrs[] = {
        &dev_attr_major.attr,
        &dev_attr_minor.attr,
        &dev_attr_optic_cpld_major.attr,
        &dev_attr_optic_cpld_devid.attr,
        &dev_attr_optic_cpld_minor.attr,
        &dev_attr_optic_cpld1_major.attr,
        &dev_attr_optic_cpld1_devid.attr,
        &dev_attr_optic_cpld1_minor.attr,
        &dev_attr_optic_cpld1_access.attr,
        &dev_attr_optic_cpld2_access.attr,
        NULL,
};

static struct attribute_group garnet_attr_group = {
        .attrs  = garnet_attrs,
};

#if GARNET_DO_SCRATCH_TEST
static int garnet_do_fpga_test_scratch(struct garnet_fpga_data *garnet, int offset)
{
        u32 acc, val = 0xde;
        struct pci_dev *pdev = garnet->pdev;
        struct device *dev = &pdev->dev;

        /*
         * Check rw register access -> use the scratch reg.
         */
        acc = ioread32(garnet->fpga_membase + offset);
        val |= (acc & ~(0xff));
        iowrite32(val, garnet->fpga_membase + offset);
        udelay(1);
        acc = ioread32(garnet->fpga_membase + offset);
        if (acc != val) {
                dev_err(dev, "Garnet scratch(0x%x) failed: %08x.%08x!\n",
                                offset, val, acc);
                return -EIO;
        }

        /*
         * Write a sig before leaving..
         */
        val = 0xBE;
        acc = ioread32(garnet->fpga_membase + offset);
        val |= (acc & ~(0xff));
        iowrite32(val, garnet->fpga_membase + offset);
        udelay(1);

        return 0;
}

static int garnet_do_mux_select(struct garnet_fpga_data *garnet, int offset)
{
        u32 acc, val = 0x05;
        struct pci_dev *pdev = garnet->pdev;
        struct device *dev = &pdev->dev;

        /*
         * FPGA Mux Select Register
         */
        acc = ioread32(garnet->fpga_membase + offset);
        val = val << 24;
        val |= (acc & 0x00ffffff);
        iowrite32(val, garnet->fpga_membase + offset);
        udelay(1);
        acc = ioread32(garnet->fpga_membase + offset);
        if (acc != val) {
                dev_err(dev, "Garnet scratch(0x%x) failed: %08x.%08x!\n",
                                offset, val, acc);
                return -EIO;
        }
        return 0;
}

static int garnet_cpld_port_led_debug(struct pci_dev *pdev,
                                        uint32_t cpld1_led_debug,
                                        uint32_t cpld2_led_debug)
{
        int spi_busy_bit;
        u8 val = 0x01, acc;
        struct device *dev = &pdev->dev;
        struct garnet_fpga_data *garnet = dev_get_drvdata(dev);

        if (!garnet) {
                dev_err(dev, "Invalid fpga driver data\n");
                return -EIO;
        }

        /* Enabling Port CPLD1 Debug Mode by setting value 1 to 0x20FC*/
        spi_busy_bit = 0;

        mutex_lock(&garnet->lock[spi_busy_bit]);
        CHECK_SPI_BUSY(garnet, spi_busy_bit);
        iowrite8(val, garnet->cpld1_membase + cpld1_led_debug);
        CHECK_SPI_BUSY(garnet, spi_busy_bit);
        acc = ioread8(garnet->cpld1_membase + cpld1_led_debug);
        CHECK_SPI_BUSY(garnet, spi_busy_bit);
        mutex_unlock(&garnet->lock[spi_busy_bit]);

        if (acc != val) {
                dev_err(dev, "Port CPLD1 LED DEBUG Mode(0x%x) failed: %08x.%08x!\n",
                                cpld1_led_debug, val, acc);
                return -EIO;
        }

        /* Enabling Port CPLD2 Debug Mode by setting value 1 to 0x30FC */
        spi_busy_bit = 1;

        mutex_lock(&garnet->lock[spi_busy_bit]);
        CHECK_SPI_BUSY(garnet, spi_busy_bit);
        iowrite8(val, garnet->cpld2_membase + cpld2_led_debug);
        CHECK_SPI_BUSY(garnet, spi_busy_bit);
        acc = ioread8(garnet->cpld2_membase + cpld2_led_debug);
        CHECK_SPI_BUSY(garnet, spi_busy_bit);
        mutex_unlock(&garnet->lock[spi_busy_bit]);

        if (acc != val) {
                dev_err(dev, "Port CPLD2 LED DEBUG Mode(0x%x) failed: %08x.%08x!\n",
                                cpld2_led_debug, val, acc);
                return -EIO;
        }

        return 0;
}

static int garnet_do_cpld_test_scratch(struct garnet_fpga_data *garnet, int offset)
{
        u32 acc;
        u8 val = 0xde;
        struct pci_dev *pdev = garnet->pdev;
        struct device *dev = &pdev->dev;
        int spi_busy_bit = ((offset & 0xFFFF) < GARNET_CPLD2_BASE) ? 0 : 1;
        void __iomem *addr = ((offset & 0xFFFF) < GARNET_CPLD2_BASE) ?
                                garnet->cpld1_membase: garnet->cpld2_membase;

        /*
         * Check rw register access -> use the scratch reg.
         */
        mutex_lock(&garnet->lock[spi_busy_bit]);
        CHECK_SPI_BUSY(garnet, spi_busy_bit)
        iowrite8(val, addr + offset);
        CHECK_SPI_BUSY(garnet, spi_busy_bit)
        acc = ioread8(addr + offset);
        CHECK_SPI_BUSY(garnet, spi_busy_bit)
        mutex_unlock(&garnet->lock[spi_busy_bit]);
        if (acc != val) {
                dev_err(dev, "Garnet cpld scratch(0x%x) failed: %08x.%08x!\n",
                                offset, val, acc);
                return -EIO;
        }

        /*
         * Write a sig before leaving..
         */
        val = 0xBE;
        mutex_lock(&garnet->lock[spi_busy_bit]);
        CHECK_SPI_BUSY(garnet, spi_busy_bit)
        iowrite8(val, addr + offset);
        CHECK_SPI_BUSY(garnet, spi_busy_bit)
        mutex_unlock(&garnet->lock[spi_busy_bit]);

        return 0;
}
#endif /* GARNET_DO_SCRATCH_TEST */

static int garnet_read_fpga_cpld_version(struct pci_dev *pdev)
{
        struct device *dev = &pdev->dev;
        struct garnet_fpga_data *garnet = dev_get_drvdata(dev);

        if (!garnet) {
                dev_err(dev, "Invalid drv data, FPGA/CPLD version read failed\n");
                return -EIO;
        }

        garnet->major = (ioread32(garnet->fpga_membase) >> (8*GARNET_FPGA_MAJOR)) & 0xFF;
        garnet->minor = (ioread32(garnet->fpga_membase) >> (8*GARNET_FPGA_MINOR)) & 0xFF;

        dev_info(dev, "Garnet FPGA Revision: 0x%02X.%02X\n",
                        garnet->major, garnet->minor);

        mutex_lock(&garnet->lock[0]);
        CHECK_SPI_BUSY(garnet, 0)
        garnet->ocpld[0].optic_cpld_major =
                ioread8(garnet->cpld1_membase + GARNET_CPLD1_BASE +
                                GARNET_OPTIC_CPLD_MAJOR);
        CHECK_SPI_BUSY(garnet, 0)
        garnet->ocpld[0].optic_cpld_minor =
                ioread8(garnet->cpld1_membase + GARNET_CPLD1_BASE +
                                GARNET_OPTIC_CPLD_MINOR);
        mutex_unlock(&garnet->lock[0]);

        dev_info(dev, "Garnet optic cpld0 Major: 0x%02X.0x%02X\n",
                        garnet->ocpld[0].optic_cpld_major,
                        garnet->ocpld[0].optic_cpld_minor);

        mutex_lock(&garnet->lock[1]);
        CHECK_SPI_BUSY(garnet, 1)
        garnet->ocpld[1].optic_cpld_major =
                ioread8(garnet->cpld2_membase + GARNET_CPLD2_BASE +
                                GARNET_OPTIC_CPLD_MAJOR);
        CHECK_SPI_BUSY(garnet, 1)
        garnet->ocpld[1].optic_cpld_minor =
                ioread8(garnet->cpld2_membase + GARNET_CPLD2_BASE +
                                GARNET_OPTIC_CPLD_MINOR);
        mutex_unlock(&garnet->lock[1]);

        dev_info(dev, "Garnet optic cpld1 Major: 0x%02X.0x%02X\n",
                        garnet->ocpld[1].optic_cpld_major,
                        garnet->ocpld[1].optic_cpld_minor);

        return 0;
}

static int garnet64_add_mfd_devices(struct pci_dev *pdev)
{
        int err, i;
        struct device *dev = &pdev->dev;
        struct garnet_fpga_data *garnet = dev_get_drvdata(dev);
        static garnet_i2c_pdata_t garnet_port_pdata[66];

#define GARNET_I2C_PORT_BUS_BASE  0x40  /* PORT0=bus64 .. PORT65=bus129 */

        if (!garnet) {
                dev_err(dev, "Invalid fpga driver data\n");
                return -EIO;
        }

        /* Assign static I2C bus numbers to each port adapter via per-port pdata */
        for (i = 0; i < 32; i++) {
                garnet_port_pdata[i] = garnet_i2c_pvt_data;
                garnet_port_pdata[i].i2c_bus_num = GARNET_I2C_PORT_BUS_BASE + i;
                garnet64_cpld1_mfd_i2c_devs[i].platform_data = &garnet_port_pdata[i];
                garnet64_cpld1_mfd_i2c_devs[i].pdata_size = sizeof(garnet_port_pdata[i]);
        }
        for (i = 32; i < 66; i++) {
                garnet_port_pdata[i] = garnet_i2c_pvt_data;
                garnet_port_pdata[i].i2c_bus_num = GARNET_I2C_PORT_BUS_BASE + i;
                garnet64_cpld2_mfd_i2c_devs[i - 32].platform_data = &garnet_port_pdata[i];
                garnet64_cpld2_mfd_i2c_devs[i - 32].pdata_size = sizeof(garnet_port_pdata[i]);
        }

        /*
         * FPGA MFDs
         */
        err = mfd_add_devices(dev, pdev->bus->number,
                        &garnet64_fpga_mfd_devs[0],
                        ARRAY_SIZE(garnet64_fpga_mfd_devs),
                        &pdev->resource[0],
                        0, NULL /* garnet->irq_domain */);
        if (err < 0) {
                dev_err(&pdev->dev, "Failed to add FPGA mfd devices %d\n", err);
                return -EIO;
        }
        /*
         * CPLD1 MFDs
         */
        err = mfd_add_devices(dev, pdev->bus->number,
                        &garnet64_cpld1_mfd_devs[0],
                        ARRAY_SIZE(garnet64_cpld1_mfd_devs),
                        &pdev->resource[1],
                        0, NULL /* garnet->irq_domain */);
        if (err < 0) {
                dev_err(&pdev->dev, "Failed to add CPLD1 mfd devices %d\n", err);
                return -EIO;
        }

        /*
         * CPLD2 MFDs
         */
        err = mfd_add_devices(dev, pdev->bus->number,
                        &garnet64_cpld2_mfd_devs[0],
                        ARRAY_SIZE(garnet64_cpld2_mfd_devs),
                        &pdev->resource[2],
                        0, NULL /* garnet->irq_domain */);
        if (err < 0) {
                dev_err(&pdev->dev, "Failed to add CPLD2 mfd devices %d\n", err);
                return -EIO;
        }

#ifdef QFX_SONIC
        /*
         * Setup I2C MFDs from CPLD1 and CPLD2
         */
        for (i = 0; i < 2 /*GARNET64_PORT_COUNT*/; i++) {
                if (i < 32) {
                        garnet64_resource_i2c[i].name = "i2c-garnet";
                        garnet64_resource_i2c[i].flags = IORESOURCE_MEM;
                        garnet64_resource_i2c[i].start =
                                GARNET64_I2C_OCORES_CPLD1_START + 0x20*i;
                        garnet64_resource_i2c[i].end =
                                GARNET64_I2C_OCORES_CPLD1_END + 0x20*i;

                        garnet64_cpld1_mfd_i2c_devs[i].name = "ocores-i2c-garnet";
                        garnet64_cpld1_mfd_i2c_devs[i].num_resources = 1;
                        garnet64_cpld1_mfd_i2c_devs[i].resources =
                                &garnet64_resource_i2c[i];
                        garnet64_cpld1_mfd_i2c_devs[i].id = i;
                } else {
                        garnet64_resource_i2c[i].name = "i2c-garnet";
                        garnet64_resource_i2c[i].flags = IORESOURCE_MEM;
                        garnet64_resource_i2c[i].start =
                                (GARNET64_I2C_OCORES_CPLD2_START +
                                 0x20*(i-32));
                        garnet64_resource_i2c[i].end =
                                (GARNET64_I2C_OCORES_CPLD2_END +
                                 0x20*(i-32));
                        garnet64_cpld2_mfd_i2c_devs[i-32].name = "ocores-i2c-garnet";
                        garnet64_cpld2_mfd_i2c_devs[i-32].num_resources = 1;
                        garnet64_cpld2_mfd_i2c_devs[i-32].resources =
                                &garnet64_resource_i2c[i];
                        garnet64_cpld2_mfd_i2c_devs[i-32].id = i;
                }
        }

#endif

        /*
         * CPLD1-I2C MFDs
         */
        err = mfd_add_devices(dev, pdev->bus->number,
                        &garnet64_cpld1_mfd_i2c_devs[0],
                        ARRAY_SIZE(garnet64_cpld1_mfd_i2c_devs),
                        &pdev->resource[1],
                        0, NULL /* garnet->irq_domain */);
        if (err < 0) {
                dev_err(&pdev->dev, "Failed to add CPLD1 I2C mfd devices %d\n", err);
                return -EIO;
        }

        /*
         * CPLD2-I2C MFDs
         */
        err = mfd_add_devices(dev, pdev->bus->number,
                        &garnet64_cpld2_mfd_i2c_devs[0],
                        ARRAY_SIZE(garnet64_cpld2_mfd_i2c_devs),
                        &pdev->resource[2],
                        0, NULL /* garnet->irq_domain */);
        if (err < 0) {
                dev_err(&pdev->dev, "Failed to add CPLD2 I2C mfd devices %d\n", err);
                return -EIO;
        }

        return 0;
}

static int garnet32_add_mfd_devices(struct pci_dev *pdev)
{
        int err, i; 
        uint32_t ports_cpld1 = GARNET32_NUM_PORTS_CPLD1;
        uint32_t ports_cpld2 = GARNET32_NUM_PORTS_CPLD2;
        struct device *dev = &pdev->dev;
        struct garnet_fpga_data *garnet = dev_get_drvdata(dev);

        if (!garnet) {
                dev_err(dev, "Invalid fpga driver data\n");
                return -EIO;
        }

        /*
         * FPGA MFDs
         */
        err = mfd_add_devices(dev, pdev->bus->number,
                        &garnet32_fpga_mfd_devs[0],
                        ARRAY_SIZE(garnet32_fpga_mfd_devs),
                        &pdev->resource[0],
                        0, NULL /* garnet->irq_domain */);
        if (err < 0) {
                dev_err(&pdev->dev, "Failed to add FPGA mfd devices %d\n", err);
                return -EIO;
        }

        /*
         * CPLD1 MFDs
         */
        err = mfd_add_devices(dev, pdev->bus->number,
                        &garnet32_cpld1_mfd_devs[0],
                        ARRAY_SIZE(garnet32_cpld1_mfd_devs),
                        &pdev->resource[1],
                        0, NULL /* garnet->irq_domain */);
        if (err < 0) {
                dev_err(&pdev->dev, "Failed to add CPLD1 mfd devices %d\n", err);
                return -EIO;
        }

        /*
         * CPLD2 MFDs
         */
        err = mfd_add_devices(dev, pdev->bus->number,
                        &garnet32_cpld2_mfd_devs[0],
                        ARRAY_SIZE(garnet32_cpld2_mfd_devs),
                        &pdev->resource[2],
                        0, NULL /* garnet->irq_domain */);
        if (err < 0) {
                dev_err(&pdev->dev, "Failed to add CPLD2 mfd devices %d\n", err);
                return -EIO;
        }

        /*
         * Setup I2C MFDs from CPLD1 and CPLD2
         */

        /* Populate the offsets for front panel 800G ports */
        for (i = 0; i < GARNET32_INBAND_PORT_START; i++) {
                sprintf(garnet32_i2c_dev_str[i], "i2c-dev-%02d", i);
                garnet32_resource_i2c[i].name = "ocores-i2c";
                garnet32_resource_i2c[i].flags = IORESOURCE_MEM;
                if (i < ports_cpld1) {
                        garnet32_resource_i2c[i].start =
                                GARNET32_I2C_OCORES_CPLD1_START +
                                GARNET32_CPLD_OCORES_OFFSET *i;
                        garnet32_resource_i2c[i].end =
                                GARNET32_I2C_OCORES_CPLD1_END +
                                GARNET32_CPLD_OCORES_OFFSET *i;
                } else {
                        garnet32_resource_i2c[i].start =
                                (GARNET32_I2C_OCORES_CPLD2_START +
                                 GARNET32_CPLD_OCORES_OFFSET *(i-ports_cpld1));
                        garnet32_resource_i2c[i].end =
                                (GARNET32_I2C_OCORES_CPLD2_END +
                                 GARNET32_CPLD_OCORES_OFFSET *(i-ports_cpld1));
                }
        }

        /* Populate the offsets for Inband ports */
        for (i = GARNET32_INBAND_PORT_START; i < GARNET32_PORT_COUNT; i++) {
                sprintf(garnet32_i2c_dev_str[i], "i2c-dev-%02d", i);
                garnet32_resource_i2c[i].name = "ocores-i2c";
                garnet32_resource_i2c[i].flags = IORESOURCE_MEM;
                garnet32_resource_i2c[i].start =
                                GARNET32_I2C_OCORES_CPLD2_START +
                                GARNET32_CPLD_OCORES_INBAND_OFFSET +
                                (GARNET32_CPLD_OCORES_OFFSET *
                                (i - GARNET32_INBAND_PORT_START));
                garnet32_resource_i2c[i].end =
                                GARNET32_I2C_OCORES_CPLD2_END +
                                GARNET32_CPLD_OCORES_INBAND_OFFSET +
                                (GARNET32_CPLD_OCORES_OFFSET *
                                (i - GARNET32_INBAND_PORT_START));
        }

        for (i = 0; i < GARNET32_PORT_COUNT; i++) {
                if (i < ports_cpld1) {
                        garnet32_cpld1_mfd_i2c_devs[i].name =
                                garnet32_i2c_dev_str[i];
                        garnet32_cpld1_mfd_i2c_devs[i].num_resources = 1;
                        garnet32_cpld1_mfd_i2c_devs[i].resources =
                                &garnet32_resource_i2c[i];
                        garnet32_cpld1_mfd_i2c_devs[i].of_compatible =
                                "opencores,i2c-ocores-garnet";
                        garnet32_cpld1_mfd_i2c_devs[i].id = 0;
                } else {
                        garnet32_cpld2_mfd_i2c_devs[i-ports_cpld1].name
                                = garnet32_i2c_dev_str[i];
                        garnet32_cpld2_mfd_i2c_devs[i-ports_cpld1].num_resources
                                = 1;
                        garnet32_cpld2_mfd_i2c_devs[i-ports_cpld1].resources
                                = &garnet32_resource_i2c[i];
                        garnet32_cpld2_mfd_i2c_devs[i-ports_cpld1].of_compatible
                                = "opencores,i2c-ocores-garnet";
                        garnet32_cpld2_mfd_i2c_devs[i-ports_cpld1].id = 0;
                }
        }

        /*
         * CPLD1-I2C MFDs
         */
        err = mfd_add_devices(dev, pdev->bus->number,
                        &garnet32_cpld1_mfd_i2c_devs[0], ports_cpld1,
                        &pdev->resource[1],
                        0, NULL /* garnet->irq_domain */);
        if (err < 0) {
                dev_err(&pdev->dev, "Failed to add CPLD1 I2C mfd devices %d\n", err);
                return -EIO;
        }

        /*
         * CPLD2-I2C MFDs
         */
        err = mfd_add_devices(dev, pdev->bus->number,
                        &garnet32_cpld2_mfd_i2c_devs[0], ports_cpld2,
                        &pdev->resource[2],
                        0, NULL /* garnet->irq_domain */);
        if (err < 0) {
                dev_err(&pdev->dev, "Failed to add CPLD2 I2C mfd devices %d\n", err);
                return -EIO;
        }

        return 0;
}

static int garnet_do_fpga_cpld_scratch_test(struct pci_dev *pdev)
{
#if defined(GARNET_DO_SCRATCH_TEST)
        int err;
        struct device *dev = &pdev->dev;
        struct garnet_fpga_data *garnet = dev_get_drvdata(dev);

        if (!garnet) {
                dev_err(dev, "Invalid fpga driver data\n");
                return -EIO;
        }

        dev_info(dev, "Garnet FPGA starting scratch test\n");
        err = garnet_do_fpga_test_scratch(garnet, GARNET_FPGA_SCRATCH_REG);
        if (err) {
                dev_err(dev, "Garnet FPGA scratch test failed\n");
                return -EIO;
        }
        dev_info(dev, "Garnet FPGA scratch test passed !!!\n");

        dev_info(dev, "Garnet CPLD0 starting scratch test\n");
        err = garnet_do_cpld_test_scratch(garnet, GARNET_CPLD1_SCRATCH_REG);
        if (err) {
                dev_err(dev, "Garnet CPLD1 scratch test failed\n");
                return -EIO;
        }
        dev_info(dev, "Garnet CPLD0 scratch test passed !!!\n");

        dev_info(dev, "Garnet CPLD1 starting scratch test\n");
        err = garnet_do_cpld_test_scratch(garnet, GARNET_CPLD2_SCRATCH_REG);
        if (err) {
                dev_err(dev, "Garnet CPLD2 scratch test failed\n");
                return -EIO;
        }
        dev_info(dev, "Garnet CPLD1 scratch test passed !!!\n");
#endif /* GARNET_DO_SCRATCH_TEST */

        return 0;
}

static int garnet_fpga_probe(struct pci_dev *pdev,
                const struct pci_device_id *id)
{
        u32 val = 0x0;
        int err, i;
        struct garnet_fpga_data *garnet;
        struct device *dev = &pdev->dev;

        dev_dbg(dev, "Garnet FPGA Probe called\n");

        garnet = devm_kzalloc(dev, sizeof(*garnet), GFP_KERNEL);
        if (!garnet)
                return -ENOMEM;

        err = pcim_enable_device(pdev);
        if (err) {
                dev_err(&pdev->dev, "Failed to enable device %d\n", err);
                return err;
        }

        /*
         * FPGA:  BAR0
         * CPLD1: BAR1
         * CPLD2: BAR2
         */
        err = pcim_iomap_regions(pdev, 0x07, "garnet-core");
        if (err) {
                dev_err(&pdev->dev, "Failed to iomap regions %d\n", err);
                goto err_disable;
        }

        garnet->fpga_membase = pcim_iomap_table(pdev)[0];
        if (IS_ERR(garnet->fpga_membase)) {
                dev_err(dev, "pci_ioremap_bar(0) failed\n");
                err = -ENOMEM;
                goto err_release;
        }

        garnet->no_lock = false;

        garnet->cpld1_membase = pcim_iomap_table(pdev)[1];
        if (IS_ERR(garnet->cpld1_membase)) {
                dev_err(dev, "pci_ioremap_bar(1) failed\n");
                err = -ENOMEM;
                goto err_release;
        }

        garnet->cpld2_membase = pcim_iomap_table(pdev)[2];
        if (IS_ERR(garnet->cpld2_membase)) {
                dev_err(dev, "pci_ioremap_bar(2) failed\n");
                err = -ENOMEM;
                goto err_release;
        }

        garnet->pdev = pdev;
        for (i = 0; i < OPTIC_CPLDS_MAX; i++) {
                mutex_init(&garnet->lock[i]);
        }
        dev_info(&pdev->dev, "Initialized mutex lock for cpld acess \n");

        pci_set_drvdata(pdev, garnet);

        /* All Garnet uses MSI interrupts - enable bus mastering */
        pci_enable_msi(pdev);
        pci_set_master(pdev);

        /* Disable ACPI processing of child nodes if they aren't set
         * properly by the Bios.
         */
        if (ACPI_COMPANION(dev)) {
                switch (pdev->device) {
                case PCI_DEVICE_ID_GARNET:
                case PCI_DEVICE_ID_GARNET32:
                        ACPI_COMPANION_SET(dev, NULL);
                        break;
                default:
                        break;
                }
        }


        err = garnet_do_fpga_cpld_scratch_test(pdev);
        if (err)
                goto err_unmap;

        val = ioread32(garnet->fpga_membase + 0x4);
        val &= ~(1 << 8);
        iowrite32(val, garnet->fpga_membase + 0x4);

        msleep(1000);
        val |=  (1 << 8);
        iowrite32(val, garnet->fpga_membase + 0x4);
        dev_info(dev, "Garnet PLL Reset \n");

        err = garnet_do_mux_select(garnet, 0x0c);
        if (err)
                goto err_unmap;
        dev_info(dev, "Garnet FPGA Mux Select Success !!!\n");

        err = garnet_read_fpga_cpld_version(pdev);
        if (err)
                goto err_unmap;

        err = sysfs_create_group(&pdev->dev.kobj, &garnet_attr_group);
        if (err) {
                sysfs_remove_group(&pdev->dev.kobj, &garnet_attr_group);
                dev_err(&pdev->dev, "Failed to create attr group\n");
                goto err_unmap;
        }

        if (id->device == PCI_DEVICE_ID_GARNET) {
                if (garnet->major >= GARNET64_FPGA_VER_SPI_LOCK_MAJOR &&
                        garnet->minor >= GARNET64_FPGA_VER_SPI_LOCK_MINOR) {
                        dev_info(&pdev->dev, "Not using locks for CPLD access\n");
                        garnet->no_lock = true;
                }

                /* Enabling Debug Mode for Port CPLD*/
                err = garnet_cpld_port_led_debug(pdev,
                                GARNET64_GPIO_CPLD1_PORT_LED_DEBUG,
                                GARNET64_GPIO_CPLD2_PORT_LED_DEBUG);
                if (err)
                        goto err_unmap;

                err = garnet64_add_mfd_devices(pdev);
                if (err)
                        goto err_remove_mfd;
        } else if (id->device == PCI_DEVICE_ID_GARNET32) {
                garnet->no_lock = true;

                /* Enabling Debug Mode for Port CPLD*/
                err = garnet_cpld_port_led_debug(pdev,
                                GARNET32_GPIO_CPLD1_PORT_LED_DEBUG,
                                GARNET32_GPIO_CPLD2_PORT_LED_DEBUG);
                if (err)
                        goto err_unmap;

                err = garnet32_add_mfd_devices(pdev);
                if (err)
                        goto err_remove_mfd;
        }

        return 0;

err_remove_mfd:
        mfd_remove_devices(dev);
err_unmap:
        pci_iounmap(pdev, garnet->fpga_membase);
        pci_iounmap(pdev, garnet->cpld1_membase);
        pci_iounmap(pdev, garnet->cpld2_membase);
err_release:
        pci_release_regions(pdev);
err_disable:
        pci_disable_device(pdev);

        return err;
}

static void garnet_fpga_remove(struct pci_dev *pdev)
{
        sysfs_remove_group(&pdev->dev.kobj, &garnet_attr_group);
        mfd_remove_devices(&pdev->dev);
}

static const struct pci_device_id garnet_fpga_id_tbl[] = {
        { PCI_DEVICE(PCI_VENDOR_ID_ACCTON, PCI_DEVICE_ID_GARNET) },
        { PCI_DEVICE(PCI_VENDOR_ID_ACCTON, PCI_DEVICE_ID_GARNET32) },
        { }
};
MODULE_DEVICE_TABLE(pci, garnet_fpga_id_tbl);

static struct pci_driver garnet_fpga_driver = {
        .name           = "garnet-core",
        .id_table       = garnet_fpga_id_tbl,
        .probe          = garnet_fpga_probe,
        .remove         = garnet_fpga_remove,
};

module_pci_driver(garnet_fpga_driver);

MODULE_DESCRIPTION("Juniper GARNET FPGA MFD core driver");
MODULE_AUTHOR("Arun kumar <arunkumara@juniper.net>");
MODULE_LICENSE("GPL");
