/* SPDX-License-Identifier: GPL-2.0 */
/*
 * jnx-wq.h --- jnx wq shim interface
 * Copyright (C) 2023 Juniper Networks Inc.
 * Author: Debjit Ghosh <dghosh@juniper.net>
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 as
 * published by the Free Software Foundation.
 */

#ifndef __JNX_WORKQUEUE_H__
#define __JNX_WORKQUEUE_H__

#include <linux/workqueue.h>

extern struct workqueue_struct *jnx_wq;

/**
 * jnx_schedule_work_on - put work task on a specific cpu
 */
static inline bool jnx_schedule_work_on(int cpu, struct work_struct *work)
{
        return queue_work_on(cpu, jnx_wq, work);
}

/**
 * jnx_schedule_work - put work task in jnx system workqueue
 */
static inline bool jnx_schedule_work(struct work_struct *work)
{
        return queue_work_on(WORK_CPU_UNBOUND, jnx_wq, work);
}

/**
 * jnx_schedule_delayed_work_on - queue work in jnx workqueue on CPU after delay
 */
static inline bool jnx_schedule_delayed_work_on(int cpu,
                                                struct delayed_work *dwork,
                                                unsigned long delay)
{
        return queue_delayed_work_on(cpu, jnx_wq, dwork, delay);
}

/**
 * jnx_schedule_delayed_work - put work task in jnx workqueue after delay
 */
static inline bool jnx_schedule_delayed_work(struct delayed_work *dwork,
                                             unsigned long delay)
{
        return queue_delayed_work_on(WORK_CPU_UNBOUND, jnx_wq, dwork, delay);
}

#endif /* __JNX_WORKQUEUE_H__ */
