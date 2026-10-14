// SPDX-License-Identifier: GPL-2.0
/*
 * I2C multiplexer
 *
 * Copyright (c) 2008-2009 Rodolfo Giometti <giometti@linux.it>
 * Copyright (c) 2008-2009 Eurotech S.p.A. <info@eurotech.it>
 *
 * This module supports the PCA954x and PCA984x series of I2C multiplexer/switch
 * chips made by NXP Semiconductors.
 * This includes the:
 *       PCA9540, PCA9542, PCA9543, PCA9544, PCA9545, PCA9546, PCA9547,
 *       PCA9548, PCA9846, PCA9847, PCA9848 and PCA9849.
 *
 * These chips are all controlled via the I2C bus itself, and all have a
 * single 8-bit register. The upstream "parent" bus fans out to two,
 * four, or eight downstream busses or channels; which of these
 * are selected is determined by the chip type and register contents. A
 * mux can select only one sub-bus at a time; a switch can select any
 * combination simultaneously.
 *
 * Based on:
 *      qfx5241_pca954x.c from Kumar Gala <galak@kernel.crashing.org>
 * Copyright (C) 2006
 *
 * Based on:
 *      qfx5241_pca954x.c from Ken Harrenstien
 * Copyright (C) 2004 Google, Inc. (Ken Harrenstien)
 *
 * Based on:
 *      i2c-virtual_cb.c from Brian Kuschak <bkuschak@yahoo.com>
 * and
 *      pca9540.c from Jean Delvare <jdelvare@suse.de>.
 */

#include <linux/device.h>
#include <linux/delay.h>
#include <linux/gpio/consumer.h>
#include <linux/i2c.h>
#include <linux/i2c-mux.h>
#include <linux/interrupt.h>
#include <linux/irq.h>
#include <linux/module.h>
#include <linux/pm.h>
#include <linux/property.h>
#include <linux/version.h>
#include <linux/slab.h>
#include <linux/spinlock.h>
#include <dt-bindings/mux/mux.h>

#define PCA954X_MAX_NCHANS 8

#define PCA954X_IRQ_OFFSET 4

struct chip_desc {
        u8 nchans;
        u8 enable;      /* used for muxes only */
        u8 has_irq;
        enum muxtype {
                qfx5241_pca954x_ismux = 0,
                qfx5241_pca954x_isswi
        } muxtype;
        struct i2c_device_identity id;
};

struct qfx5241_pca954x {
        const struct chip_desc *chip;

        int smbus_transaction_type;

        u8 last_chan;           /* last register value */
        /* MUX_IDLE_AS_IS, MUX_IDLE_DISCONNECT or >= 0 for channel */
        s32 idle_state;

        struct i2c_client *client;

        struct irq_domain *irq;
        unsigned int irq_mask;
        raw_spinlock_t lock;
};

/* Provide specs for the PCA954x types we know about */
static const struct chip_desc chips[] = {
        [0] = {
                .nchans = 8,
                .muxtype = qfx5241_pca954x_isswi,
                .id = { .manufacturer_id = I2C_DEVICE_ID_NONE },
        },
};

static const struct i2c_device_id qfx5241_pca954x_id[] = {
        { "pca9548_jnx", 0 },
        { }
};
MODULE_DEVICE_TABLE(i2c, qfx5241_pca954x_id);

/*
 * Static I2C bus number assignments derived from hardware topology.
 * Each MUX has a unique I2C address; channels are numbered consecutively
 * starting from first_bus.  Must match pddf-device.json virt_bus values.
 *
 *  MUX1 @ 0x78 (iSMT bus 0x00): channels 0-7 → buses 0x10..0x17
 *  MUX2 @ 0x70 (iSMT bus 0x00): channels 0-7 → buses 0x20..0x27
 *  MUX3 @ 0x76 (MUX2 ch0 bus 0x20): channels 0-7 → buses 0x30..0x37
 */
static const struct {
        unsigned short addr;
        u32 first_bus;
} qfx5241_mux_bus_map[] = {
        { 0x78, 0x10 },
        { 0x70, 0x20 },
        { 0x76, 0x30 },
};

/* Write to mux register. Don't use i2c_transfer()/i2c_smbus_xfer()
   for this as they will try to lock adapter a second time */
static int qfx5241_pca954x_reg_write(struct i2c_adapter *adap,
                             struct i2c_client *client, u8 val, int smbus_transaction_type)
{
        if(smbus_transaction_type == I2C_SMBUS_BYTE_DATA) {
                union i2c_smbus_data data = {.byte = val};

                return __i2c_smbus_xfer(adap, client->addr, client->flags,
                                        I2C_SMBUS_WRITE, 0,
                                        I2C_SMBUS_BYTE_DATA, &data);
        }

        union i2c_smbus_data dummy;

        return __i2c_smbus_xfer(adap, client->addr, client->flags,
                                I2C_SMBUS_WRITE, val,
                                I2C_SMBUS_BYTE, &dummy);
}

static u8 qfx5241_pca954x_regval(struct qfx5241_pca954x *data, u8 chan)
{
        /* We make switches look like muxes, not sure how to be smarter. */
        if (data->chip->muxtype == qfx5241_pca954x_ismux)
                return chan | data->chip->enable;
        else
                return 1 << chan;
}

static int qfx5241_pca954x_select_chan(struct i2c_mux_core *muxc, u32 chan)
{
        struct qfx5241_pca954x *data = i2c_mux_priv(muxc);
        struct i2c_client *client = data->client;
        u8 regval;
        int ret = 0;

        regval = qfx5241_pca954x_regval(data, chan);
        /* Only select the channel if its different from the last channel */
        if (data->last_chan != regval) {
                ret = qfx5241_pca954x_reg_write(muxc->parent, client, regval,data->smbus_transaction_type);
                data->last_chan = ret < 0 ? 0 : regval;
        }

        return ret;
}

static int qfx5241_pca954x_deselect_mux(struct i2c_mux_core *muxc, u32 chan)
{
        struct qfx5241_pca954x *data = i2c_mux_priv(muxc);
        struct i2c_client *client = data->client;
        s32 idle_state;

        idle_state = READ_ONCE(data->idle_state);
        if (idle_state >= 0)
                /* Set the mux back to a predetermined channel */
                return qfx5241_pca954x_select_chan(muxc, idle_state);

        if (idle_state == MUX_IDLE_DISCONNECT) {
                /* Deselect active channel */
                data->last_chan = 0;
                return qfx5241_pca954x_reg_write(muxc->parent, client,
                                         data->last_chan,data->smbus_transaction_type);
        }

        /* otherwise leave as-is */

        return 0;
}

static ssize_t idle_state_show(struct device *dev,
                                    struct device_attribute *attr,
                                    char *buf)
{
        struct i2c_client *client = to_i2c_client(dev);
        struct i2c_mux_core *muxc = i2c_get_clientdata(client);
        struct qfx5241_pca954x *data = i2c_mux_priv(muxc);

        return sprintf(buf, "%d\n", READ_ONCE(data->idle_state));
}

static ssize_t idle_state_store(struct device *dev,
                                struct device_attribute *attr,
                                const char *buf, size_t count)
{
        struct i2c_client *client = to_i2c_client(dev);
        struct i2c_mux_core *muxc = i2c_get_clientdata(client);
        struct qfx5241_pca954x *data = i2c_mux_priv(muxc);
        int val;
        int ret;

        ret = kstrtoint(buf, 0, &val);
        if (ret < 0)
                return ret;

        if (val != MUX_IDLE_AS_IS && val != MUX_IDLE_DISCONNECT &&
            (val < 0 || val >= data->chip->nchans))
                return -EINVAL;

        i2c_lock_bus(muxc->parent, I2C_LOCK_SEGMENT);

        WRITE_ONCE(data->idle_state, val);
        /*
         * Set the mux into a state consistent with the new
         * idle_state.
         */
        if (data->last_chan || val != MUX_IDLE_DISCONNECT)
                ret = qfx5241_pca954x_deselect_mux(muxc, 0);

        i2c_unlock_bus(muxc->parent, I2C_LOCK_SEGMENT);

        return ret < 0 ? ret : count;
}

static DEVICE_ATTR_RW(idle_state);

static irqreturn_t qfx5241_pca954x_irq_handler(int irq, void *dev_id)
{
        struct qfx5241_pca954x *data = dev_id;
        unsigned long pending;
        int ret, i;

        ret = i2c_smbus_read_byte(data->client);
        if (ret < 0)
                return IRQ_NONE;

        pending = (ret >> PCA954X_IRQ_OFFSET) & (BIT(data->chip->nchans) - 1);
        for_each_set_bit(i, &pending, data->chip->nchans)
                handle_nested_irq(irq_linear_revmap(data->irq, i));

        return IRQ_RETVAL(pending);
}

static int qfx5241_pca954x_irq_set_type(struct irq_data *idata, unsigned int type)
{
        if ((type & IRQ_TYPE_SENSE_MASK) != IRQ_TYPE_LEVEL_LOW)
                return -EINVAL;
        return 0;
}

static struct irq_chip qfx5241_pca954x_irq_chip = {
        .name = "i2c-mux-qfx5241_pca954x",
        .irq_set_type = qfx5241_pca954x_irq_set_type,
};

static int qfx5241_pca954x_irq_setup(struct i2c_mux_core *muxc)
{
        struct qfx5241_pca954x *data = i2c_mux_priv(muxc);
        struct i2c_client *client = data->client;
        int c, irq;

        if (!data->chip->has_irq || client->irq <= 0)
                return 0;

        raw_spin_lock_init(&data->lock);

        data->irq = irq_domain_add_linear(client->dev.of_node,
                                          data->chip->nchans,
                                          &irq_domain_simple_ops, data);
        if (!data->irq)
                return -ENODEV;

        for (c = 0; c < data->chip->nchans; c++) {
                irq = irq_create_mapping(data->irq, c);
                if (!irq) {
                        dev_err(&client->dev, "failed irq create map\n");
                        return -EINVAL;
                }
                irq_set_chip_data(irq, data);
                irq_set_chip_and_handler(irq, &qfx5241_pca954x_irq_chip,
                        handle_simple_irq);
        }

        return 0;
}

static void qfx5241_pca954x_cleanup(struct i2c_mux_core *muxc)
{
        struct qfx5241_pca954x *data = i2c_mux_priv(muxc);
        int c, irq;

        if (data->irq) {
                for (c = 0; c < data->chip->nchans; c++) {
                        irq = irq_find_mapping(data->irq, c);
                        irq_dispose_mapping(irq);
                }
                irq_domain_remove(data->irq);
        }
        i2c_mux_del_adapters(muxc);
}

static int qfx5241_pca954x_init(struct i2c_client *client, struct qfx5241_pca954x *data)
{
        int ret;

        if (data->idle_state >= 0)
                data->last_chan = qfx5241_pca954x_regval(data, data->idle_state);
        else
                data->last_chan = 0; /* Disconnect multiplexer */

        ret = i2c_smbus_write_byte(client, data->last_chan);
        if (ret < 0)
                data->last_chan = 0;

        return ret;
}

/*
 * I2C init/probing/exit functions
 */
static int qfx5241_pca954x_probe(struct i2c_client *client
#if LINUX_VERSION_CODE < KERNEL_VERSION(6, 6, 0)
			 , const struct i2c_device_id *id
#endif
			 )
{
	struct i2c_adapter *adap = client->adapter;
	struct device *dev = &client->dev;
	struct gpio_desc *gpio;
	struct i2c_mux_core *muxc;
	struct qfx5241_pca954x *data;
	int num;
	int ret;
	u32 first_bus = 0;
	int k;

#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 6, 0)
	const struct i2c_device_id *id = i2c_client_get_device_id(client);
#endif

	/* Look up static first bus number for this MUX based on its I2C address */
	for (k = 0; k < ARRAY_SIZE(qfx5241_mux_bus_map); k++) {
		if (client->addr == qfx5241_mux_bus_map[k].addr) {
			first_bus = qfx5241_mux_bus_map[k].first_bus;
			break;
		}
	}

        muxc = i2c_mux_alloc(adap, dev, PCA954X_MAX_NCHANS, sizeof(*data), 0,
                             qfx5241_pca954x_select_chan, qfx5241_pca954x_deselect_mux);
        if (!muxc)
                return -ENOMEM;
        data = i2c_mux_priv(muxc);

        i2c_set_clientdata(client, muxc);
        data->client = client;

        /* Reset the mux if a reset GPIO is specified. */
        gpio = devm_gpiod_get_optional(dev, "reset", GPIOD_OUT_HIGH);
        if (IS_ERR(gpio))
                return PTR_ERR(gpio);
        if (gpio) {
                udelay(1);
                gpiod_set_value_cansleep(gpio, 0);
                /* Give the chip some time to recover. */
                udelay(1);
        }

        data->chip = device_get_match_data(dev);
        if (!data->chip)
                data->chip = &chips[id->driver_data];

        if (data->chip->id.manufacturer_id != I2C_DEVICE_ID_NONE) {
                struct i2c_device_identity id;

                ret = i2c_get_device_id(client, &id);
                if (ret && ret != -EOPNOTSUPP)
                        return ret;

                if (!ret &&
                    (id.manufacturer_id != data->chip->id.manufacturer_id ||
                     id.part_id != data->chip->id.part_id)) {
                        dev_warn(dev, "unexpected device id %03x-%03x-%x\n",
                                 id.manufacturer_id, id.part_id,
                                 id.die_revision);
                        return -ENODEV;
                }
        }

        data->idle_state = MUX_IDLE_AS_IS;
        data->idle_state = MUX_IDLE_DISCONNECT;
        /*
         * Write the mux register at addr to verify
         * that the mux is in fact present. This also
         * initializes the mux to a channel
         * or disconnected state.
         */
        ret = qfx5241_pca954x_init(client, data);
        if (ret < 0) {
                dev_warn(dev, "probe failed\n");
                return -ENODEV;
        }

        data->smbus_transaction_type = I2C_SMBUS_BYTE_DATA;
        ret = qfx5241_pca954x_irq_setup(muxc);
        if (ret)
                goto fail_cleanup;

        /* Now create an adapter for each channel */
        for (num = 0; num < data->chip->nchans; num++) {
                u32 force_nr = first_bus ? (first_bus + num) : 0;

#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 6, 0)
                ret = i2c_mux_add_adapter(muxc, force_nr, num);
#else
                ret = i2c_mux_add_adapter(muxc, force_nr, num, 0);
#endif
                if (ret)
                        goto fail_cleanup;
        }

        if (data->irq) {
                ret = devm_request_threaded_irq(dev, data->client->irq,
                                                NULL, qfx5241_pca954x_irq_handler,
                                                IRQF_ONESHOT | IRQF_SHARED,
                                                "qfx5241_pca954x", data);
                if (ret)
                        goto fail_cleanup;
        }

        /*
         * The attr probably isn't going to be needed in most cases,
         * so don't fail completely on error.
         */
        device_create_file(dev, &dev_attr_idle_state);

        dev_info(dev, "registered %d multiplexed busses for I2C %s %s\n",
                 num, data->chip->muxtype == qfx5241_pca954x_ismux
                                ? "mux" : "switch", client->name);

        return 0;

fail_cleanup:
        qfx5241_pca954x_cleanup(muxc);
        return ret;
}

static void qfx5241_pca954x_remove(struct i2c_client *client)
{
        struct i2c_mux_core *muxc = i2c_get_clientdata(client);

        device_remove_file(&client->dev, &dev_attr_idle_state);

        qfx5241_pca954x_cleanup(muxc);
}

#ifdef CONFIG_PM_SLEEP
static int qfx5241_pca954x_resume(struct device *dev)
{
        struct i2c_client *client = to_i2c_client(dev);
        struct i2c_mux_core *muxc = i2c_get_clientdata(client);
        struct qfx5241_pca954x *data = i2c_mux_priv(muxc);
        int ret;

        ret = qfx5241_pca954x_init(client, data);
        if (ret < 0)
                dev_err(&client->dev, "failed to verify mux presence\n");

        return ret;
}
#endif

static SIMPLE_DEV_PM_OPS(qfx5241_pca954x_pm, NULL, qfx5241_pca954x_resume);

static struct i2c_driver qfx5241_pca954x_driver = {
        .driver         = {
                .name   = "pca9548_jnx",
                .pm     = &qfx5241_pca954x_pm,
        },
        .probe          = qfx5241_pca954x_probe,
        .remove         = qfx5241_pca954x_remove,
        .id_table       = qfx5241_pca954x_id,
};

module_i2c_driver(qfx5241_pca954x_driver);

MODULE_AUTHOR("Rodolfo Giometti <giometti@linux.it>");
MODULE_DESCRIPTION("PCA954x I2C mux/switch driver");
MODULE_LICENSE("GPL v2");
