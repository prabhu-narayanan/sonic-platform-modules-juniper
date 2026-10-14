// SPDX-License-Identifier: GPL-2.0-only
/*
 * Jnx workqueue shim driver
 *
 * drivers/jnx/jnx-wq.c
 *
 * Copyright (C) 2023 Juniper Networks Inc.
 * Author: Debjit Ghosh <dghosh@juniper.net>
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

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/signal.h>
#include <linux/completion.h>
#include <linux/workqueue.h>
#include <linux/slab.h>
#include <linux/notifier.h>
#include <linux/kthread.h>
#include <linux/err.h>
#include <linux/notifier.h>
#include <linux/delay.h>
#include "jnx-wq.h"

struct workqueue_struct *jnx_wq;
EXPORT_SYMBOL(jnx_wq);

static int __init jnx_wq_init(void)
{
        /*
         * allocate a global workqueue for all drivers that needs
         * to schedule a work
         */
        jnx_wq = alloc_ordered_workqueue("jnx-wq", WQ_MEM_RECLAIM);

        if (WARN_ON(!jnx_wq))
                return -ENOMEM;

        pr_info("jnx wq initialized\n");

        return 0;
}

static void __exit jnx_wq_exit(void)
{
        flush_workqueue(jnx_wq);
        destroy_workqueue(jnx_wq);
        jnx_wq = NULL;
}

module_init(jnx_wq_init);
module_exit(jnx_wq_exit);

MODULE_DESCRIPTION("Juniper Inc. Jnx workqueue shim driver");
MODULE_AUTHOR("Debjit Ghosh <dghosh@juniper.net>");
MODULE_LICENSE("GPL");
MODULE_ALIAS("platform:jnx-wq");
