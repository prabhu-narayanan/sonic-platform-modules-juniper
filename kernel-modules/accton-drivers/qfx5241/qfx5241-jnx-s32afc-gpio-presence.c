/*
 * drivers/gpio/jnx-s32afc-gpio-presence.c
 * I2C -> GPIO mapping driver
 * Copyright (c) 2018 Juniper Networks
 * Author: Diwas Kumar <diwask@juniper.net>
 *
 * This driver maps register bits to GPIOs, which can be used to define the
 * state of FRU(Fan) presence.
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; version 2 of the License.
 *
 */

#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/pci.h>
#include <linux/gpio.h>
#include <linux/interrupt.h>
#include <linux/irqdomain.h>
#include <linux/errno.h>
#include <linux/of_device.h>
#include <linux/of_platform.h>
#include <linux/of_gpio.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/sched.h>
#include <linux/platform_device.h>
#include <linux/version.h>
#include <linux/regmap.h>
#include "../common/jnx-tmc.h"
#include <linux/of_irq.h>
#include "qfx5241-jnx-s32afc-core.h"

#define ALTERA_FAN_INTR_NR_GROUPS       1
#define ALTERA_FAN_INTR_MAX_IRQS_PG     32

#define ALTERA_FAN_IRQ_MAX_BITS_PER_REG         32
#define ALTERA_FAN_IRQ_MAX_INTRS                                \
        (ALTERA_FAN_INTR_MAX_IRQS_PG * ALTERA_FAN_INTR_NR_GROUPS)

#define ALTERA_FAN_IRQ_GPIO_TO_GROUP(irq)                       \
                        ((irq) / ALTERA_FAN_IRQ_MAX_BITS_PER_REG)
#define ALTERA_FAN_IRQ_GPIO_TO_IRQBIT(irq)              \
                        ((irq) % ALTERA_FAN_IRQ_MAX_BITS_PER_REG)

#define SET_GPIO_BIT(p, n) ((p) |= (1 << (n)))
#define CLR_GPIO_BIT(p, n) ((p) &= (~((1) << (n))))

#define FAN_GPIO_COUNT     32
#define FAN_PRESENT_REG    0X07
struct altera_fan_irq_group {
        int start;          /* 1st gpio pin */
        int count;          /* # of pins in group */
        u32 val;
        u32 mask;
};

struct altera_fan_irq_chip {
        int     i2c_reg;
        struct device *dev;
        struct regmap *regmap;
        struct gpio_chip gpio;
        char   label_name[20];
        struct irq_domain *domain;
        struct mutex irq_lock;     /* irq lock */
        struct mutex work_lock;     /* work lock */
        struct delayed_work work;
        struct altera_fan_irq_group irq_group[ALTERA_FAN_INTR_NR_GROUPS];
        int ngpio;
        int irq;
        unsigned long grpmask;
        u8 irq_type[ALTERA_FAN_IRQ_MAX_INTRS];
        unsigned long poll_interval;
        bool polling;
        u32 cur_state;
        u32 prev_state;
        u32 fan_presence;
};

#define gpio_to_altera_fan_chip(chip) \
        container_of((chip), struct altera_fan_irq_chip, gpio)

#define worker_to_altera_fan_chip(worker) \
        container_of((worker), struct altera_fan_irq_chip, work.work)

/*
 * altera_fan_irq_status - Read the status for the interrupt pin.
 */
static int altera_fan_irq_status(struct gpio_chip *gc, unsigned int gpio)
{
        struct altera_fan_irq_chip *chip = gpio_to_altera_fan_chip(gc);
        struct altera_fan_irq_group *irq_group;
        unsigned int group = ALTERA_FAN_IRQ_GPIO_TO_GROUP(gpio);
        unsigned int bit   = ALTERA_FAN_IRQ_GPIO_TO_IRQBIT(gpio);

        dev_dbg(chip->dev, "ALTERA_FAN IRQ status %u, %u, %u\n",
                gpio, group, bit);

        if (group > ALTERA_FAN_INTR_NR_GROUPS ||
            bit > ALTERA_FAN_IRQ_MAX_BITS_PER_REG)
                return 0;

        irq_group = &chip->irq_group[group];

        return (irq_group->val & BIT(bit));
}

static int altera_fan_irq_gpio_to_irq(struct gpio_chip *gc, unsigned int offset)
{
        struct altera_fan_irq_chip *chip = gpio_to_altera_fan_chip(gc);

        dev_dbg(chip->dev, "irq gpio to irq offset %u\n", offset);

        return irq_create_mapping(chip->domain, offset);
}

static int altera_fan_irq_dir_inp(struct gpio_chip *gc, unsigned nr)
{
        /* do nothing for interrupt pins */
        return 0;
}

static int altera_fan_irq_dir_outp(struct gpio_chip *gc, unsigned nr, int val)
{
        /* do nothing for interrupt pins */
        return 0;
}

static int altera_fan_irq_getdir(struct gpio_chip *chip, unsigned offset)
{
	return GPIOD_IN;
}

static void altera_fan_irq_mask(struct irq_data *data)
{
        struct altera_fan_irq_chip *chip = irq_data_get_irq_chip_data(data);
        u32 group   = ALTERA_FAN_IRQ_GPIO_TO_GROUP(data->hwirq);
        u32 bit     = ALTERA_FAN_IRQ_GPIO_TO_IRQBIT(data->hwirq);

        if (group > ALTERA_FAN_INTR_NR_GROUPS ||
            bit > ALTERA_FAN_IRQ_MAX_BITS_PER_REG)
                return;

        dev_dbg(chip->dev, "irq mask group:%u gpio:%u\n", group, bit);
        CLR_GPIO_BIT(chip->irq_group[group].mask, bit);
}

static void altera_fan_irq_unmask(struct irq_data *data)
{
        struct altera_fan_irq_chip *chip = irq_data_get_irq_chip_data(data);
        u32 group   = ALTERA_FAN_IRQ_GPIO_TO_GROUP(data->hwirq);
        u32 bit     = ALTERA_FAN_IRQ_GPIO_TO_IRQBIT(data->hwirq);

        if (group > ALTERA_FAN_INTR_NR_GROUPS ||
            bit > ALTERA_FAN_IRQ_MAX_BITS_PER_REG)
                return;

        dev_dbg(chip->dev, "irq unmask group:%u gpio:%u\n", group, bit);
        SET_GPIO_BIT(chip->irq_group[group].mask, bit);
}

static int altera_fan_irq_set_type(struct irq_data *data, unsigned int type)
{
        return 0;
}

static void altera_fan_irq_bus_lock(struct irq_data *data)
{
        struct altera_fan_irq_chip *chip = irq_data_get_irq_chip_data(data);

        mutex_lock(&chip->irq_lock);
}

static void altera_fan_irq_bus_sync_unlock(struct irq_data *data)
{
        struct altera_fan_irq_chip *chip = irq_data_get_irq_chip_data(data);

        /* Synchronize interrupts to chip */
        mutex_unlock(&chip->irq_lock);
}

static struct irq_chip altera_fan_irq_irqchip = {
        .name = "irq-altera_fan",
        .irq_mask = altera_fan_irq_mask,
        .irq_unmask = altera_fan_irq_unmask,
        .irq_set_type = altera_fan_irq_set_type,
        .irq_bus_lock = altera_fan_irq_bus_lock,
        .irq_bus_sync_unlock = altera_fan_irq_bus_sync_unlock,
};

static int altera_fan_irq_map(struct irq_domain *domain,
                            unsigned int irq, irq_hw_number_t hwirq)
{
        irq_set_chip_data(irq, domain->host_data);
        irq_set_chip(irq, &altera_fan_irq_irqchip);
        irq_set_nested_thread(irq, true);
        irq_set_noprobe(irq);

        return 0;
}

static const struct irq_domain_ops altera_fan_irq_domain_ops = {
        .map    = altera_fan_irq_map,
        .xlate  = irq_domain_xlate_twocell,
};

/*
 * Fan Presence Status reg of ALTERA FAN CPLD represents bit 0:31 for
 * Fan 0 to Fan 15 presence and absence. Here, 32 bit value represent the
 * presence and absence GPIO. example as below.
 * fan0 presence -> bit 0 (32 bit GPIO)
 * fan0 absence -> bit 16 (32 bit GPIO)
 * fan1 present -> bit 1 (32 bit GPIO)
 * fan1 absence -> bit 17 (32 bit GPIO)
 *
 * Presence is active low. That means a bit value of 0 represents Fan Module is
 * present and a bit value of 1 means Fan Module is absent
 */
static bool altera_fan_irq_group_work(struct altera_fan_irq_chip *chip,
                                        u8 group)
{
        u32 cur_bit;
        u32 prev_bit;
        struct altera_fan_irq_group *irq_group = &chip->irq_group[group];
        irq_hw_number_t gpio;
        int virq;
        int i, ret;

        ret = regmap_read(chip->regmap, chip->fan_presence,
                                &(chip->cur_state));
        if (ret < 0)
                return ret;

/* Invert all the bits of presence reg since its active low */
        chip->cur_state = ~chip->cur_state;

        if (chip->cur_state != chip->prev_state) {
                dev_dbg(chip->dev, "Altera Fan state change cur: %x, prev: %x\n",
                        chip->cur_state, chip->prev_state);
                /* find the toggle bit */
                for (i = 0; i < 16; i++) {
                        cur_bit = (chip->cur_state & BIT(i));
                        prev_bit = (chip->prev_state & BIT(i));
                        if (cur_bit != prev_bit) {
                                if (cur_bit) {
                                        SET_GPIO_BIT(irq_group->val, i);
                                        CLR_GPIO_BIT(irq_group->val, i+16);
                                        if (irq_group->mask & BIT(i)) {
                                                gpio = i;
                                                virq =
                                                irq_find_mapping(chip->domain,
                                                                gpio);
                                                handle_nested_irq(virq);
                                                dev_dbg(chip->dev, "Altera Fan "
                                                " handle IRQ: %lu\n", gpio);
                                        }
                                } else {
                                        SET_GPIO_BIT(irq_group->val, i+16);
                                        CLR_GPIO_BIT(irq_group->val, i);
                                        if (irq_group->mask & BIT(i+16)) {
                                                gpio = i+16;
                                                virq =
                                                irq_find_mapping(chip->domain,
                                                                gpio);
                                                handle_nested_irq(virq);
                                                dev_dbg(chip->dev, "Altera Fan"
                                                " handle IRQ: %lu\n", gpio);
                                        }
                                }
                        }
                }
                chip->prev_state = chip->cur_state;
        }

        return true;
}

static irqreturn_t altera_fan_irq_work(struct altera_fan_irq_chip *chip)
{
        u16 pos;
        bool handled = false;
        irqreturn_t ret = IRQ_NONE;

        mutex_lock(&chip->work_lock);

        WARN_ON(!chip->polling);
        for_each_set_bit(pos, &chip->grpmask, fls(chip->grpmask)) {
                handled = altera_fan_irq_group_work(chip, pos);
                if (handled)
                        ret = IRQ_HANDLED;
        }
        mutex_unlock(&chip->work_lock);

        return ret;
}

static irqreturn_t altera_fan_irq_handler(int irq, void *data)
{
        irqreturn_t ret = IRQ_NONE;

        ret = altera_fan_irq_work((struct altera_fan_irq_chip *)data);

        return ret;
}

static void altera_fan_irq_worker(struct work_struct *work)
{
        struct altera_fan_irq_chip *chip = worker_to_altera_fan_chip(work);

        altera_fan_irq_work(chip);
        schedule_delayed_work(&chip->work,
                              msecs_to_jiffies(chip->poll_interval));
}

static void altera_fan_irq_teardown(struct device *dev,
                                  struct altera_fan_irq_chip *chip)
{
        int i, irq;

        for (i = 0; i < chip->ngpio; i++) {
                irq = irq_find_mapping(chip->domain, i);
                if (irq > 0)
                        irq_dispose_mapping(irq);
        }
        irq_domain_remove(chip->domain);
}

static void altera_fan_irq_chip_init(struct altera_fan_irq_chip *chip)
{
        u8 group;
        u8 bit;

        for (group = 0; group < ALTERA_FAN_INTR_NR_GROUPS; group++) {
                /* Mask all */
                for (bit = 0; bit < ALTERA_FAN_IRQ_MAX_BITS_PER_REG; bit++) {
                        CLR_GPIO_BIT(chip->irq_group[group].mask, bit);
                }
        }
}

static void altera_fan_irq_gpio_setup(struct altera_fan_irq_chip *chip)
{
        struct gpio_chip *gpio = &chip->gpio;

        gpio->base      = -1;
        gpio->ngpio     = chip->ngpio;
        gpio->label     = chip->label_name;
        gpio->parent    = chip->dev;
        gpio->dbg_show  = NULL;
        gpio->can_sleep = 0;
        /*
         * Kernel GPIO API drift:
         * - gpio_chip::of_node was removed; modern kernels use fwnode.
         */
#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 6, 0)
        gpio->fwnode = dev_fwnode(chip->dev);
#elif defined(CONFIG_OF_GPIO)
        gpio->of_node   = chip->dev->of_node;
#endif
        gpio->owner     = THIS_MODULE;
        gpio->get       = altera_fan_irq_status;
        gpio->to_irq    = altera_fan_irq_gpio_to_irq;
        gpio->set               = NULL;
        gpio->get_direction     = altera_fan_irq_getdir;
        gpio->direction_input   = altera_fan_irq_dir_inp;
        gpio->direction_output  = altera_fan_irq_dir_outp;
        gpio->set_config        = NULL;
}

static int altera_fan_irq_setup(struct device *dev,
                              struct altera_fan_irq_chip *chip)
{
        int err;

        chip->domain = irq_domain_add_linear(dev->of_node,
                                             chip->ngpio,
                                             &altera_fan_irq_domain_ops,
                                             chip);

        if (!chip->domain)
                return -ENOMEM;

        INIT_DELAYED_WORK(&chip->work, altera_fan_irq_worker);

        if (chip->irq > 0) {
                dev_dbg(dev, "Setting up interrupt %d\n", chip->irq);
                err = devm_request_threaded_irq(dev, chip->irq, NULL,
                                                altera_fan_irq_handler,
                                                IRQF_ONESHOT,
                                                dev_name(dev), chip);
                if (err)
                        goto err_remove_domain;
        } else {
                chip->polling = true;
                schedule_delayed_work(&chip->work, 1);
        }

        return 0;

err_remove_domain:
        irq_domain_remove(chip->domain);
        chip->domain = NULL;

        return err;
}

static int altera_fan_irq_of_init(struct device *dev,
                                struct altera_fan_irq_chip *chip)
{
        u32 value;
        int i, err;
        u32 group, count;

#ifdef QFX_SONIC
        if (of_have_populated_dt() && !dev->of_node) {
                dev_err(dev, "No device node\n");
                return -ENODEV;
        }

        err = of_property_read_u32(dev->of_node, "gpio-count", &value);
        if (err)
                return err;

        value = FAN_GPIO_COUNT;
        if (value > ALTERA_FAN_IRQ_MAX_INTRS)
                value = ALTERA_FAN_IRQ_MAX_INTRS;
        chip->ngpio = value;

        chip->fan_presence = ALTERA_FAN_MODULE_PRESENT_REG;
        /* Pick Fan presence reg from device tree if present*/
        if (dev->of_node) {
                of_property_read_u32(dev->of_node, "fan-presence-reg",
                                        &chip->fan_presence);
        }
#endif
        chip->ngpio = FAN_GPIO_COUNT;
        chip->fan_presence = FAN_PRESENT_REG;

        snprintf(chip->label_name, sizeof(chip->label_name), "%s", "fan-presence");
        
        /* make all of them till gpio count */
        for (i = 0; i < chip->ngpio; i++) {
                group = ALTERA_FAN_IRQ_GPIO_TO_GROUP(i);
                count = ALTERA_FAN_IRQ_GPIO_TO_IRQBIT(i);
                chip->irq_group[group].start = 0;
                chip->irq_group[group].count = (count + 1);
                chip->grpmask |= BIT(group);
                chip->irq_group[group].val = 0;
                chip->irq_group[group].mask = 0;
        }
#ifdef QFX_SONIC
        /*
         * poll-interval - on boards that doesn't support interrupts
         * Default poll interval is 1000 msec
         */
        err = of_property_read_u32(dev->of_node, "poll-interval", &value);
        if (err)
                value = 1000;
#endif
        value = 1000;
        chip->poll_interval = value;

        return 0;
}

static int altera_fan_irq_probe(struct platform_device *pdev)
{
        struct device *dev = &pdev->dev;
        struct altera_fan_irq_chip *chip;
        int err;
        struct device_node *np = dev->of_node;


#ifdef QFX_SONIC
        if (!of_find_property(dev->of_node, "interrupt-controller", NULL))
                return -ENODEV;
#endif
        chip = devm_kzalloc(dev, sizeof(*chip), GFP_KERNEL);
        if (!chip)
                return -ENOMEM;

        chip->regmap = dev_get_regmap(dev->parent, NULL);
        if (!chip->regmap) {
                dev_err(dev, "Failed to get regmap from parent device");
                return -ENODEV;
        }
        err = altera_fan_irq_of_init(dev, chip);
        if (err)
                return err;

        chip->dev = dev;
        chip->irq = irq_of_parse_and_map(np, 0);

        mutex_init(&chip->irq_lock);
        mutex_init(&chip->work_lock);

        altera_fan_irq_chip_init(chip);
        altera_fan_irq_gpio_setup(chip);
        err = altera_fan_irq_setup(dev, chip);
        if (err < 0)
                return err;
#ifdef QFX_SONIC
        if (of_find_property(dev->of_node, "gpio-controller", NULL)) {
                err = gpiochip_add(&chip->gpio);
                if (err) {
                        dev_err(dev,
                                "Failed to register Altera Fan irq gpio : %d\n",
                                err);
                        goto err_teardown;
                }
        }
#endif
        /* gpiochip_add() was replaced by gpiochip_add_data() on newer kernels */
#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 6, 0)
        err = gpiochip_add_data(&chip->gpio, chip);
#else
        err = gpiochip_add(&chip->gpio);
#endif
        if (err) {
                dev_err(dev,
                        "Failed to register Altera Fan irq gpio : %d\n",
                        err);
                goto err_teardown;
        }
        platform_set_drvdata(pdev, chip);
        return 0;

err_teardown:
        if (chip->domain)
                altera_fan_irq_teardown(dev, chip);

        return err;
}

#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 6, 0)
static void altera_fan_irq_remove(struct platform_device *pdev)
#else
static int altera_fan_irq_remove(struct platform_device *pdev)
#endif
{
        struct altera_fan_irq_chip *chip = platform_get_drvdata(pdev);
        struct device *dev = &pdev->dev;

        cancel_delayed_work_sync(&chip->work);
        if (chip->domain)
                altera_fan_irq_teardown(dev, chip);
        gpiochip_remove(&chip->gpio);

#if LINUX_VERSION_CODE < KERNEL_VERSION(6, 6, 0)
        return 0;
#endif
}

static const struct of_device_id altera_fan_irq_ids[] = {
        { .compatible = "jnx,s32afc-fan-presence", },
        { },
};
MODULE_DEVICE_TABLE(of, altera_fan_irq_ids);

static struct platform_driver altera_fan_irq_driver = {
        .driver = {
                .name = "s32afc-fan-presence",
                .owner  = THIS_MODULE,
                .of_match_table = altera_fan_irq_ids,
        },
        .probe = altera_fan_irq_probe,
        .remove = altera_fan_irq_remove,
};

module_platform_driver(altera_fan_irq_driver);

MODULE_DESCRIPTION("Juniper Altera CPLD Fan Presence GPIO driver");
MODULE_AUTHOR("Diwas Kumar <diwask@juniper.net>");
MODULE_LICENSE("GPL");
