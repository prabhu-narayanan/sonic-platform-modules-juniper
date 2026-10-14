/*
 * Juniper Networks TMC fpga PSU driver
 *
 * This driver is for detecting if the PSU is present or not
 *
 * Copyright (C) 2025 Juniper Networks
 * Author: Satish Gopalakrishnan <satishg@juniper.net>
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 */

#include <linux/module.h>
#include <linux/init.h>
#include <linux/device.h>
#include <linux/delay.h>
#include <linux/platform_device.h>
#include <linux/io.h>
#include <linux/hwmon.h>
#include <linux/mutex.h>
#include <linux/kernel.h>
#include <linux/hwmon-sysfs.h>
#include <linux/errno.h>
#include <linux/string.h>
#include <linux/version.h>

/* Max PSUs supported by this driver */
#define NUM_PSU         2

struct qfx5241_jnx_garnet_psu_data {
    int num_psu;
    void __iomem *tmc_membase;
};

enum sysfs_psu_attributes {
    PSU0_PRESENT,
    PSU1_PRESENT,
};

/*
 * Garnet PSM presence address is 0x7 but since we need to use
 * 32-bit addresses, we need to collate register 0x4 till 0x7
 * in a single 32 bit read and derive bit position based on that.
 * The presence bits are active low which means that if the presence
 * bit is 0 then the PSU is present.
 */
static bool get_psu_presense(void *addr, u8 idx)
{
    u32 value = ioread32(addr + 0x4);
    u8 reg_0x7 = (value >> 24) & 0xFF;

    // Inverted logic: 0 = present, 1 = absent
    return !(reg_0x7 & BIT(idx));
}

/*
 * Sysfs files are present in this path
 * /sys/bus/platform/devices/garnet-psu.2/psu*_present
 */

#define DECLARE_PSU_PRESENT_SENSOR_DEV_ATTR(index) \
    static SENSOR_DEVICE_ATTR(psu##index##_present, S_IRUGO, qfx5241_jnx_garnet_psu_presense_show, NULL, PSU##index##_PRESENT)
#define DECLARE_PSU_PRESENT_ATTR(index)      &sensor_dev_attr_psu##index##_present.dev_attr.attr

static ssize_t qfx5241_jnx_garnet_psu_presense_show(struct device *dev, struct device_attribute *attr, char *buf)
{
    struct sensor_device_attribute *s_attr = to_sensor_dev_attr(attr);
    struct platform_device *pdev = to_platform_device(dev);
    struct qfx5241_jnx_garnet_psu_data *psu = platform_get_drvdata(pdev);

    return sprintf(buf, "%d\n", get_psu_presense(psu->tmc_membase, s_attr->index));
}

DECLARE_PSU_PRESENT_SENSOR_DEV_ATTR(0);
DECLARE_PSU_PRESENT_SENSOR_DEV_ATTR(1);

static struct attribute *qfx5241_jnx_garnet_psu_attrs[] = {
    DECLARE_PSU_PRESENT_ATTR(0),
    DECLARE_PSU_PRESENT_ATTR(1),
    NULL
};

static struct attribute_group qfx5241_jnx_garnet_psu_attr_group = {
    .attrs = qfx5241_jnx_garnet_psu_attrs,
};

static int qfx5241_jnx_garnet_psu_probe(struct platform_device *pdev)
{
    struct device *dev = &pdev->dev;
    struct qfx5241_jnx_garnet_psu_data *psu;
    int ret;
    struct resource *res;
    void __iomem *addr;

    psu = devm_kzalloc(dev, sizeof(*psu), GFP_KERNEL);
    if (!psu) {
        dev_err(dev, "psu structure allocation failed\n");
        return -ENOMEM;
    }

    res = platform_get_resource(pdev, IORESOURCE_MEM, 0);
    if (!res) {
        dev_err(dev, "res allocation failed\n");
        return -ENODEV;
    }

    addr = devm_ioremap(dev, res->start, resource_size(res));
    if (!addr) {
        dev_err(dev, "ioremap failed\n");
        return -ENOMEM;
    }

    psu->tmc_membase = addr;
    psu->num_psu = NUM_PSU;

    platform_set_drvdata(pdev, psu);

    ret = sysfs_create_group(&dev->kobj, &qfx5241_jnx_garnet_psu_attr_group);
    if (ret != 0) {
        dev_err(dev, "jnx-tmc-psu: sysfs_create_group failed: %d\n", ret);
        return ret;
    } 

    return 0;
}

#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 6, 0)
static void qfx5241_jnx_garnet_psu_remove(struct platform_device *pdev)
#else
static int qfx5241_jnx_garnet_psu_remove(struct platform_device *pdev)
#endif
{
    struct qfx5241_jnx_garnet_psu_data *psu = platform_get_drvdata(pdev);

    if (psu) {
        devm_kfree(&pdev->dev, psu);
    }
    sysfs_remove_group(&pdev->dev.kobj, &qfx5241_jnx_garnet_psu_attr_group);

#if LINUX_VERSION_CODE < KERNEL_VERSION(6, 6, 0)
    return 0;
#endif
}

static struct platform_driver qfx5241_jnx_core_psu_driver = {
    .driver = {
        .name  = "garnet-psu",
        .owner  = THIS_MODULE,
    },
    .probe = qfx5241_jnx_garnet_psu_probe,
    .remove = qfx5241_jnx_garnet_psu_remove,
};

static int __init qfx5241_jnx_core_psu_driver_init(void)
{
    int ret = -1;

    ret = platform_driver_register(&qfx5241_jnx_core_psu_driver);

    return ret;
}

static void __exit qfx5241_jnx_core_psu_driver_exit(void)
{
    platform_driver_unregister(&qfx5241_jnx_core_psu_driver);
}

module_init(qfx5241_jnx_core_psu_driver_init);
module_exit(qfx5241_jnx_core_psu_driver_exit);

MODULE_DESCRIPTION("Juniper Networks Garnet PSU driver");
MODULE_AUTHOR("Satish Gopalakrishnan <satishg@juniper.net>");
MODULE_LICENSE("GPL");
