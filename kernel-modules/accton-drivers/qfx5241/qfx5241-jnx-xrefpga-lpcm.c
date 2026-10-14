/*
 * Juniper Networks XRE FPGA over LPC multi-function core driver
 *
 * drivers/mfd/jnx-xrefpga-lpcm.c
 *
 * Copyright (c) 2020, Juniper Networks
 * Author: Vaibhav Agarwal <avaibhav@juniper.net>
 *
 * The XRE FPGA MFD core driver for Juniper hardware.
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

#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/device.h>
#include <linux/delay.h>
#include <linux/module.h>
#include <linux/io.h>
#include <linux/interrupt.h>
#include <linux/irqdomain.h>
#include <linux/acpi.h>
#include <linux/of.h>
#include <linux/of_device.h>
#include <linux/of_platform.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/sched.h>
#include <linux/platform_device.h>
#include <linux/mfd/core.h>
#include "qfx5241-jnx-xrefpga-lpcm.h"
#include "qfx5241-jnx-subsys.h"
#include <linux/reboot.h>
#include <linux/serial_8250.h>

#define JNX_ID_TOMATIN_MAINBOARD        0x0db2
#define REFPGA_LPC_BASE_ADDRESS         0xFC800000
#define REFPGA_LPC_WINDOW_SIZE          0x00000100

static void __iomem *fpga = NULL;

static int xrefpga_reboot_handler(struct notifier_block *,
                                  unsigned long, void *);
static struct notifier_block xrefpga_reboot_notifier = {
        .notifier_call = xrefpga_reboot_handler,
};

static int xrefpga_reboot_handler(struct notifier_block *nb,
                                  unsigned long event,
                                  void *buf)
{

        if (event != SYS_RESTART)
                return NOTIFY_OK;

        /* Reconfigure the xrefpga */
        iowrite8(JNX_XREFPGA_LPCM_UPDATE_ENABLED,
                 (u8*)fpga + JNX_XREFPGA_LPCM_FCFG_ENB);
        iowrite8(JNX_XREFPGA_LPCM_FCFG_RSTE,
                 (u8*)fpga + JNX_XREFPGA_LPCM_FCFG_WB_CTL);
        iowrite8(JNX_XREFPGA_LPCM_FCFG_WBCE,
                 (u8*)fpga + JNX_XREFPGA_LPCM_FCFG_WB_CTL);
        /* Data 0 */
        iowrite8(JNX_XREFPGA_LPCM_FCFG_DATA0,
                 (u8*)fpga + JNX_XREFPGA_LPCM_FCFG_WB_DATA);
        /* Data 1 */
        iowrite8(JNX_XREFPGA_LPCM_FCFG_DATA1,
                 (u8*)fpga + JNX_XREFPGA_LPCM_FCFG_WB_DATA);
        /* Data 2 */
        iowrite8(JNX_XREFPGA_LPCM_FCFG_DATA2,
                 (u8*)fpga + JNX_XREFPGA_LPCM_FCFG_WB_DATA);
        /* Disconnect Wishbone Interface */
        iowrite8(0x00,
                 (u8*)fpga + JNX_XREFPGA_LPCM_FCFG_WB_CTL);

        return NOTIFY_OK;
}

#if 0                               
static int xrefpga_lpcm_scratch_test(void)
{
        u8 wval, rval;
        void __iomem *scratch = (u8*)fpga + JNX_XREFPGA_LPCM_SCRATCH;

        for (wval = 0; wval != (u8)-1; wval++) {
                iowrite8(wval, (u8*)scratch);
                rval = ioread8((u8*)scratch);
                if (rval != wval) {
                        printk(KERN_ERR
                                "Scratch test failed: wr=0x%02x, rd=0x%2x\n",
                                wval, rval);
                        return -EIO;
                }
        }

        return 0;
}
#endif

static int __init xrefpga_lpcm_init(void)
{
        u8 major_version, minor_version;

        if (!request_mem_region(REFPGA_LPC_BASE_ADDRESS, REFPGA_LPC_WINDOW_SIZE, "xrefpga-lpc")) {
                printk(KERN_ERR "Cannot allocate Re-fpga memory region. Carrying ON\n");
                /* return -ENODEV; */
        }

        fpga = ioremap(REFPGA_LPC_BASE_ADDRESS, REFPGA_LPC_WINDOW_SIZE);
        if (fpga == NULL ) {
                printk(KERN_ERR "ioremap failed\n");
                return -ENOMEM;
        }
#if 0
        err = xrefpga_lpcm_scratch_test();
        if (err)
                return err;

        printk(KERN_INFO "XRE FPGA LPCM Scratch test passed !!!\n");
#endif
        printk(KERN_INFO "XRE FPGA Versions\n");
        major_version = ioread8((u8*)fpga + JNX_XREFPGA_LPCM_VERSION_MAJOR),
        minor_version = ioread8((u8*)fpga + JNX_XREFPGA_LPCM_VERSION_MINOR);
        printk(KERN_INFO "XRE FPGA version major: 0x%02X, minor: 0x%02X\n",
                 major_version, minor_version);

        iowrite8(0x22, (u8*)fpga + JNX_XREFPGA_LPCM_RST_CTL);
        msleep(1000);
        return 0;
}

static void __exit xrefpga_lpcm_exit(void)
{
        unregister_reboot_notifier(&xrefpga_reboot_notifier);
        iounmap(fpga);
        release_mem_region(REFPGA_LPC_BASE_ADDRESS, REFPGA_LPC_WINDOW_SIZE);
        printk(KERN_INFO "XRE-Fpga lpcm module removed\n");
}


module_init(xrefpga_lpcm_init);
module_exit(xrefpga_lpcm_exit);

MODULE_DESCRIPTION("Juniper XRE FPGA MFD Core Driver");
MODULE_AUTHOR("Vaibhav Agarwal <avaibhav@juniper.net>");
MODULE_LICENSE("GPL");
MODULE_ALIAS("platform:xrefpga-lpcm");
