/*
 * Juniper Networks RE-FPGA qfx platform specific driver
 *
 * Copyright (C) 2018 Juniper Networks
 * Author: Ciju Rajan K <crajank@juniper.net>
 *
 * This driver implements various features such as
 *  - ALARM led driver
 *  - Fan full speed reset control
 *  - Any new QFX specific features which uses RE-FPGA
 *
 * This driver is based on I2CS fpga LEDs driver by Georgi Vlaev
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 */

#include <linux/module.h>
#include <linux/of.h>
#include <linux/delay.h>
#include <linux/leds.h>
#include <linux/platform_device.h>
#include <linux/io.h>
#include <linux/mutex.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/pci.h>
#include <linux/gpio.h>
#include <linux/interrupt.h>
#include <linux/irqdomain.h>
#include <linux/errno.h>
/*#include <linux/jnx/jnx-subsys.h>*/
#include <linux/string.h>

#define NUM_LEDS					7 /* Max number of Alarm + FAN LEDs */

#define ALARM_MINOR_LED				0
#define ALARM_MAJOR_LED				1

#define REFPGA_PCIE_RESET_CTRL		0x13
#define REFPGA_PCIE_ALARM			0x33
#define REFPGA_FAN0_CTRL_STAT		0x28

#define REFPGA_RESET_FAN_SPEED		BIT(3)
#define REFPGA_OPER_TYPE			BIT(0)
#define REFPGA_OPER_START			BIT(1)
#define REFPGA_OPER_DONE			BIT(2)

#define TMC_REFPGA_ADDR_REG			0x0     /* TMC offset: 0x228 */
#define TMC_REFPGA_DATA_REG			0x4     /* TMC offset: 0x22C */
#define TMC_REFPGA_CTRL_REG			0x8     /* TMC offset: 0x230 */

#define TMC_REFPGA_READ_CMD			0x3
#define TMC_REFPGA_WRITE_CMD		0x2


#define REFPGA_INTR_NR_GROUPS		1
#define REFPGA_INTR_MAX_IRQS_PG		32

#define MAX_FANS					5

#define REFPGA_IRQ_MAX_BITS_PER_REG 32
#define REFPGA_IRQ_MAX_INTRS				\
	(REFPGA_INTR_MAX_IRQS_PG * REFPGA_INTR_NR_GROUPS)

#define REFPGA_IRQ_GPIO_TO_GROUP(irq)			\
			((irq) / REFPGA_IRQ_MAX_BITS_PER_REG)
#define REFPGA_IRQ_GPIO_TO_IRQBIT(irq)		\
			((irq) % REFPGA_IRQ_MAX_BITS_PER_REG)

#define SET_GPIO_BIT(p, n) ((p) |= (1 << (n)))
#define CLR_GPIO_BIT(p, n) ((p) &= (~((1) << (n))))

/*
 * LED specific data structures
 */
struct refpga_led {
	struct led_classdev lc;
	struct work_struct work;
	int blink;
	int on;
	int bit;
	void __iomem *addr;
};

struct refpga_led_data {
	int num_leds;
	struct refpga_led *leds;
};

static DEFINE_MUTEX(alarm_led_lock);

/*
 * Structures for handling IRQs
 */
struct refpga_irq_group {
	int start;	    /* 1st gpio pin */
	int count;	    /* # of pins in group */
	u32 val;
	u32 mask;
};

struct refpga_irq_chip {
	void __iomem *base;
	struct device *dev;
	struct gpio_chip gpio;
	struct irq_domain *domain;
	struct mutex irq_lock;     /* irq lock */
	struct mutex work_lock;	    /* work lock */
	struct delayed_work work;
	struct refpga_irq_group irq_group[REFPGA_INTR_NR_GROUPS];
	int ngpio;
	int irq;
	unsigned long grpmask;
	u8 irq_type[REFPGA_IRQ_MAX_INTRS];
	unsigned long poll_interval;
	bool polling;
};

#define gpio_to_refpga_chip(chip) \
	container_of((chip), struct refpga_irq_chip, gpio)

#define worker_to_refpga_chip(worker) \
	container_of((worker), struct refpga_irq_chip, work.work)

/*
 * Common routines
 */
struct refpga_chip {
    struct refpga_led_data *led;
    struct refpga_irq_chip *irq;
};

static struct refpga_chip *refpga;

static DEFINE_MUTEX(refpga_lock);

static void __iomem *tmc_membase;

static void wait_for_refpga_oper(void __iomem *base_addr)
{
	volatile u32 done = ~(-1);
	unsigned long int timeout;
	void __iomem *addr;

	addr = base_addr + (TMC_REFPGA_CTRL_REG);
	/*
	 * Wait till the transaction is complete
	 */
	timeout = jiffies + msecs_to_jiffies(100);

	do {
		usleep_range(50, 100);
		done = ioread32(addr);
		if (done & (REFPGA_OPER_DONE))
			break;
	} while(time_before(jiffies, timeout));
}

static u32 refpga_read(void __iomem *base_addr, u32 refpga_offset)
{
	u32 value;

	mutex_lock(&refpga_lock);
	iowrite32(refpga_offset, base_addr + (TMC_REFPGA_ADDR_REG));
	iowrite32(TMC_REFPGA_READ_CMD, base_addr + (TMC_REFPGA_CTRL_REG));
	wait_for_refpga_oper(base_addr);
	value = ioread32(base_addr + (TMC_REFPGA_DATA_REG));
	mutex_unlock(&refpga_lock);

	return value;
}

static void refpga_write(void __iomem *base_addr, u32 refpga_offset, u32 val)
{
	mutex_lock(&refpga_lock);
	iowrite32(refpga_offset, base_addr + (TMC_REFPGA_ADDR_REG));
	iowrite32(val, base_addr + (TMC_REFPGA_DATA_REG));
	iowrite32(TMC_REFPGA_WRITE_CMD, base_addr + (TMC_REFPGA_CTRL_REG));
	wait_for_refpga_oper(base_addr);
	mutex_unlock(&refpga_lock);
}

/*
 * There is only a single ALARM led in QFX5200 and that
 * is used for both Major & Minor alarm indicator.
 * These are represented by two different bits in RE-FPGA
 * PCIE_ALARM register. Only one of the bit (either Red or
 * Yellow) should be set a time. If both the bits are set,
 * it's an undefined behaviour.
 *
 * The following table describes how the conditions are
 * handled in the driver as there can be both Major & Minor
 * alarms can be triggered from userspace.
 *
 *  Major   Minor   Colour
 *
 *   0       0       Nil
 *   0       1      Yellow
 *   1       1       Red
 *   1       0       Red
 *
 */
static void manage_alarm_led(void __iomem *addr, int led_type, int value)
{
	static int alarm_major = 0, alarm_minor = 0;
	u32 reg = 0x0;

	mutex_lock(&alarm_led_lock);
	reg = refpga_read(addr, REFPGA_PCIE_ALARM);

	(led_type == ALARM_MAJOR_LED) ?
			((value == 1) ? (alarm_major = 1) : (alarm_major = 0)) :
			((value == 1) ? (alarm_minor = 1) : (alarm_minor = 0));
	if (alarm_major) {
		reg &= ~BIT(ALARM_MINOR_LED);
		reg |= BIT(ALARM_MAJOR_LED);
	} else {
		if (alarm_minor) {
			reg &= ~BIT(ALARM_MAJOR_LED);
			reg |= BIT(ALARM_MINOR_LED);
		} else {
			reg &= ~BIT(ALARM_MINOR_LED);
			reg &= ~BIT(ALARM_MAJOR_LED);
		}
	}
	refpga_write(addr, REFPGA_PCIE_ALARM, reg);
	mutex_unlock(&alarm_led_lock);
}

static void manage_fan_led(void __iomem *addr, int fan_slot, int value)
{
	u8 offset = REFPGA_FAN0_CTRL_STAT + (fan_slot * 2);
	u32 reg = 0x0;

	reg = refpga_read(addr, offset);
	if(value) {
		/* Turn on s/w control */
		reg = reg | BIT(4);
		/* Turn off green led */
		reg &= ~BIT(5);
		/* Turn on yellow led & make it blink */
		reg |= (BIT(6) | BIT(7));
	} else {
		/* Clear yellow led & stop blink */
		reg &= ~(BIT(6) | BIT(7));
		/* Stop s/w control */
		reg &= ~BIT(4);
	}
	refpga_write(addr, offset, reg);
}

static void refpga_led_work(struct work_struct *work)
{
	struct refpga_led *led = container_of(work, struct refpga_led, work);
	void __iomem *addr;

	addr = led->addr;
	
	if(strstr(led->lc.name, "fan"))
		manage_fan_led(addr, led->bit, led->on);
	else
		manage_alarm_led(addr, led->bit, led->on);
}

static void refpga_led_brightness_set(struct led_classdev *lc,
				 enum led_brightness brightness)
{
	struct refpga_led *led = container_of(lc, struct refpga_led, lc);

	led->on = (brightness != LED_OFF);
	led->blink = 0; /* always turn off hw blink on brightness_set() */
	schedule_work(&led->work);
}

static int refpga_led_init_one(struct device *dev,
				struct device_node *np,
				struct refpga_led_data *ild,
				int num)
{
	struct refpga_led *led;
	const char *string;
	int ret, reg;

	led = &ild->leds[num];
	led->addr = tmc_membase;

	if (!of_property_read_string(np, "label", &string))
		led->lc.name = string;
	else
		led->lc.name = np->name;

	if (!of_property_read_string(np, "linux,default-trigger", &string))
		led->lc.default_trigger = string;

	if (of_property_read_bool(np, "default-on"))
		led->lc.brightness = LED_FULL;
	else
		led->lc.brightness = LED_OFF;

	ret = of_property_read_u32(np, "reg", &reg);
	if (ret)
		return -ENODEV;
	led->bit = reg;

	led->lc.brightness_set = refpga_led_brightness_set;

	ret = devm_led_classdev_register(dev, &led->lc);
	if (ret) {
		dev_err(dev, "devm_led_classdev_register failed\n");
		return ret;
	}

	INIT_WORK(&led->work, refpga_led_work);

	return 0;
}

static int refpga_led_of_init(struct device *dev, struct refpga_led_data *ild)
{
	struct device_node *child, *np = dev->of_node;
	int ret, num_leds, i = 0;

	if (!dev->parent) {
		dev_err(dev, "dev->parent is null\n");
		return -ENODEV;
	}

	num_leds = of_get_child_count(np);
	if (!num_leds || num_leds > NUM_LEDS)
		return -ENODEV;

	ild->num_leds = num_leds;
	ild->leds = devm_kzalloc(dev, sizeof(struct refpga_led) * num_leds,
					GFP_KERNEL);
	if (!ild->leds) {
		dev_err(dev, "LED allocation failed\n");
		return -ENOMEM;
	}

	for_each_child_of_node(np, child) {
		ret = refpga_led_init_one(dev, child, ild, i++);
		if (ret)
			return ret;
	}

	return 0;
}

static int jnx_refpga_led_probe(struct platform_device *pdev)
{	
	struct device *dev = &pdev->dev;
	struct refpga_led_data *ild;
	int ret;

	ild = devm_kzalloc(dev, sizeof(*ild), GFP_KERNEL);
	if (!ild) {
		dev_err(dev, "ild allocation failed\n");
		return -ENOMEM;
	}

	ret = refpga_led_of_init(dev, ild);
	if (ret < 0)
		return ret;
	
	refpga->led = ild;

	return 0;
}

static int jnx_refpga_led_remove(struct platform_device *pdev)
{
	struct refpga_chip *drv_data = platform_get_drvdata(pdev);	
	struct refpga_led_data *ild = drv_data->led;
	int i;

	for (i = 0; i < ild->num_leds; i++) {
		devm_led_classdev_unregister(&pdev->dev, &ild->leds[i].lc);
		cancel_work_sync(&ild->leds[i].work);
	}
    if (ild) {
		if (ild->leds)
			devm_kfree(&pdev->dev, ild->leds);
		devm_kfree(&pdev->dev, ild);
	}
	return 0;
}

static void reset_fan_full_speed(struct device *dev)
{
	u32 val = ~(-1), tmp = ~(-1);

	/*
	 * Reading the REFPGA_PCIE_RESET_CTRL register
	 */
	val = refpga_read(tmc_membase, REFPGA_PCIE_RESET_CTRL);
	/*
	 * Clearing the fan full_speed bit
	 */
	val &= ~(REFPGA_RESET_FAN_SPEED);
	/*
	 * Writing the REFPGA_PCIE_RESET_CTRL register
	 */
	refpga_write(tmc_membase, REFPGA_PCIE_RESET_CTRL, val);
	/*
	 * Reading the REFPGA_PCIE_RESET_CTRL register
	 */
	tmp = refpga_read(tmc_membase, REFPGA_PCIE_RESET_CTRL);
	dev_info(dev, "After resetting fan full speed control: %X\n", tmp);
}

/*
 * refpga_irq_status - Read the status for the interrupt pin.
 */
static int refpga_irq_status(struct gpio_chip *gc, unsigned int gpio)
{
	struct refpga_irq_chip *chip = gpio_to_refpga_chip(gc);
	struct refpga_irq_group *irq_group;
	unsigned int group = REFPGA_IRQ_GPIO_TO_GROUP(gpio);
	unsigned int bit   = REFPGA_IRQ_GPIO_TO_IRQBIT(gpio);

	dev_dbg(chip->dev, "REFPGA IRQ status %u, %u, %u\n", gpio, group, bit);

	if (group > REFPGA_INTR_NR_GROUPS || bit > REFPGA_IRQ_MAX_BITS_PER_REG)
		return 0;

	irq_group = &chip->irq_group[group];

	return (irq_group->val & BIT(bit));
}

static int refpga_irq_gpio_to_irq(struct gpio_chip *gc, unsigned int offset)
{
	struct refpga_irq_chip *chip = gpio_to_refpga_chip(gc);
	
	dev_dbg(chip->dev, "irq gpio to irq offset %u\n", offset);

	return irq_create_mapping(chip->domain, offset);
}

static int refpga_irq_dir_inp(struct gpio_chip *gc, unsigned nr)
{
	/* do nothing for interrupt pins */
	return 0;
}

static int refpga_irq_dir_outp(struct gpio_chip *gc, unsigned nr, int val)
{
	/* do nothing for interrupt pins */
	return 0;
}

static int refpga_irq_getdir(struct gpio_chip *chip, unsigned offset)
{
	return GPIOF_DIR_IN;
}

static void refpga_irq_mask(struct irq_data *data)
{
	struct refpga_irq_chip *chip = irq_data_get_irq_chip_data(data);
	u32 group   = REFPGA_IRQ_GPIO_TO_GROUP(data->hwirq);
	u32 bit	= REFPGA_IRQ_GPIO_TO_IRQBIT(data->hwirq);

	if (group > REFPGA_INTR_NR_GROUPS || bit > REFPGA_IRQ_MAX_BITS_PER_REG)
		return;

	dev_dbg(chip->dev, "irq mask group:%u gpio:%u\n", group, bit);
	CLR_GPIO_BIT(chip->irq_group[group].mask, bit);
}

static void refpga_irq_unmask(struct irq_data *data)
{
	struct refpga_irq_chip *chip = irq_data_get_irq_chip_data(data);
 	u32 group   = REFPGA_IRQ_GPIO_TO_GROUP(data->hwirq);
	u32 bit	= REFPGA_IRQ_GPIO_TO_IRQBIT(data->hwirq);

	if (group > REFPGA_INTR_NR_GROUPS || bit > REFPGA_IRQ_MAX_BITS_PER_REG)
		return;

	dev_dbg(chip->dev, "irq unmask group:%u gpio:%u\n", group, bit);
	SET_GPIO_BIT(chip->irq_group[group].mask, bit);
}

static int refpga_irq_set_type(struct irq_data *data, unsigned int type)
{
    return 0;
}

static void refpga_irq_bus_lock(struct irq_data *data)
{
	struct refpga_irq_chip *chip = irq_data_get_irq_chip_data(data);

	mutex_lock(&chip->irq_lock);
}

static void refpga_irq_bus_sync_unlock(struct irq_data *data)
{
	struct refpga_irq_chip *chip = irq_data_get_irq_chip_data(data);

	/* Synchronize interrupts to chip */
	mutex_unlock(&chip->irq_lock);
}

static struct irq_chip refpga_irq_irqchip = {
	.name = "irq-refpga",
	.irq_mask = refpga_irq_mask,
	.irq_unmask = refpga_irq_unmask,
	.irq_set_type = refpga_irq_set_type,
	.irq_bus_lock = refpga_irq_bus_lock,
	.irq_bus_sync_unlock = refpga_irq_bus_sync_unlock,
};

static int refpga_irq_map(struct irq_domain *domain,
			    unsigned int irq, irq_hw_number_t hwirq)
{
	irq_set_chip_data(irq, domain->host_data);
	irq_set_chip(irq, &refpga_irq_irqchip);
	irq_set_nested_thread(irq, true);
 	irq_set_noprobe(irq);

	return 0;
}

static const struct irq_domain_ops refpga_irq_domain_ops = {
    .map	= refpga_irq_map,
    .xlate	= irq_domain_xlate_twocell,
};

static u32 read_refpga_fan_status(struct refpga_irq_chip *chip)
{
	u8 value[MAX_FANS] = {0x00, 0x00, 0x00, 0x00, 0x00};
	u8 offset = REFPGA_FAN0_CTRL_STAT;
	u32 bit_mask = ~(-1);
	u8 idx = 0;

    for (idx = 0; (idx < MAX_FANS); idx++) {
        value[idx] = refpga_read(tmc_membase, offset);
        /*
         * Get the last two bits of REFPGA_FANx_CTRL_STAT
         */
        value[idx] = (value[idx] & BIT(0)) | (value[idx] & BIT(1));

        if (value[idx])
            bit_mask |= BIT(idx);
        else
            bit_mask &= ~BIT(idx);

        offset += 2;
    }

    return bit_mask;
}

/*
 * REFPGA_FANx_CTRL_STAT register of REFPGA gives the fan airflow
 * status. There are 5 fans in QFX5200. Last two bits give the AFI
 * & AFO status. If any of these bits are set, fan is present.
 * Here, 32 bit value represent the presence and absence GPIO.
 *
 * fan0 present -> bit 0
 * fan0 absent  -> bit 16
 *
 * fan1 present -> bit 1
 * fan1 absent  -> bit 17
 *
 * fan2 present -> bit 2
 * fan2 absent  -> bit 18
 *
 * fan3 present -> bit 3
 * fan3 absent  -> bit 19
 *
 * fan4 present -> bit 4
 * fan4 absent  -> bit 20
 */
static bool refpga_irq_group_work(struct refpga_irq_chip *chip, u8 group)
{
	static u32 cur_state;
	static u32 prev_state;
	u32 cur_bit;
	u32 prev_bit;
	struct refpga_irq_group *irq_group = &chip->irq_group[group];
	irq_hw_number_t gpio;
	int virq;
	int i;

	cur_state = read_refpga_fan_status(chip);
	if (cur_state != prev_state) {
		dev_dbg(chip->dev, "REFPGA FAN state change cur: %x, prev: %x\n",
						cur_state, prev_state);
		/* find the toggled bit */
		for (i = 0; i < MAX_FANS; i++) {
			cur_bit = (cur_state & BIT(i));
			prev_bit = (prev_state & BIT(i));
			if (cur_bit != prev_bit) {
				if (cur_bit) {
					SET_GPIO_BIT(irq_group->val, i);
					CLR_GPIO_BIT(irq_group->val, i+16);
					if (irq_group->mask & BIT(i)) {
						gpio = i;
						virq = irq_find_mapping(chip->domain, gpio);
						handle_nested_irq(virq);
						dev_dbg(chip->dev, "REFPGA FAN"
										" handle IRQ: %lu mask: %x\n",
										gpio, irq_group->mask);
					}
				} else {
					SET_GPIO_BIT(irq_group->val, i+16);
					CLR_GPIO_BIT(irq_group->val, i);
					if (irq_group->mask & BIT(i+16)) {
						gpio = i+16;
						virq = irq_find_mapping(chip->domain, gpio);
						handle_nested_irq(virq);
						dev_dbg(chip->dev, "REFPGA FAN"
										" handle IRQ: %lu mask: %x\n",
										gpio, irq_group->mask);
					}
				}
			}
		}
		prev_state = cur_state;
	}
	return true;
}

static irqreturn_t refpga_irq_work(struct refpga_irq_chip *chip)
{
	u16 pos;
	bool handled = false;
	irqreturn_t ret = IRQ_NONE;

    mutex_lock(&chip->work_lock);

	WARN_ON(!chip->polling);
	for_each_set_bit(pos, &chip->grpmask, fls(chip->grpmask)) {
		handled = refpga_irq_group_work(chip, pos);
		if (handled)
			ret = IRQ_HANDLED;
	}
	mutex_unlock(&chip->work_lock);

    return ret;
}

static irqreturn_t refpga_irq_handler(int irq, void *data)
{
	irqreturn_t ret = IRQ_NONE;

    ret = refpga_irq_work((struct refpga_irq_chip *)data);

    return ret;
}

static void refpga_irq_worker(struct work_struct *work)
{
	struct refpga_irq_chip *chip = worker_to_refpga_chip(work);

	refpga_irq_work(chip);
	schedule_delayed_work(&chip->work,
					msecs_to_jiffies(chip->poll_interval));
}

static void refpga_irq_teardown(struct device *dev,
				  struct refpga_irq_chip *chip)
{
	int i;

	for (i = 0; i < chip->ngpio; i++) {
		int irq = irq_find_mapping(chip->domain, i);
		if (irq > 0)
			irq_dispose_mapping(irq);
	}
	irq_domain_remove(chip->domain);
}

static void refpga_irq_chip_init(struct refpga_irq_chip *chip)
{
	u8 group;
	u8 bit;

	for (group = 0; group < REFPGA_INTR_NR_GROUPS; group++) {
		/* Mask all */
		for (bit = 0; bit < REFPGA_IRQ_MAX_BITS_PER_REG; bit++) {
			CLR_GPIO_BIT(chip->irq_group[group].mask, bit);
		}
	}
}

static void refpga_irq_gpio_setup(struct refpga_irq_chip *chip)
{
    struct gpio_chip *gpio = &chip->gpio;

    gpio->base      = -1;
    gpio->ngpio	= chip->ngpio;
    gpio->label	= dev_name(chip->dev);
    gpio->parent	= chip->dev;
    gpio->dbg_show	= NULL;
    gpio->can_sleep	= 0;
#if defined(CONFIG_OF_GPIO)
    gpio->of_node	= chip->dev->of_node;
#endif /* CONFIG_OF_GPIO */
    gpio->owner	= THIS_MODULE;
    gpio->get	= refpga_irq_status;
    gpio->to_irq	= refpga_irq_gpio_to_irq;
    gpio->set		= NULL;
    gpio->get_direction	= refpga_irq_getdir;
    gpio->direction_input	= refpga_irq_dir_inp;
    gpio->direction_output	= refpga_irq_dir_outp;
    gpio->set_config	= NULL;
}

static int refpga_irq_setup(struct device *dev,
			      struct refpga_irq_chip *chip)
{
	int err;
	
	chip->domain = irq_domain_add_linear(dev->of_node,
					chip->ngpio,
					&refpga_irq_domain_ops,
					chip);
	if (!chip->domain)
		return -ENOMEM;

	INIT_DELAYED_WORK(&chip->work, refpga_irq_worker);

    if (chip->irq > 0) {
		dev_dbg(dev, "Setting up interrupt %d\n", chip->irq);
		err = devm_request_threaded_irq(dev, chip->irq,
						NULL,
						refpga_irq_handler,
						IRQF_ONESHOT,
						dev_name(dev),
						chip);
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

static int refpga_irq_of_init(struct device *dev,
				struct refpga_irq_chip *chip)
{
	u32 value;
	int i, err;
	u32 group, count;

	if (of_have_populated_dt() && !dev->of_node) {
		dev_err(dev, "No device node\n");
		return -ENODEV;
	}

	err = of_property_read_u32(dev->of_node, "gpio-count", &value);
	if (err)
		return err;

	if (value > REFPGA_IRQ_MAX_INTRS)
		value = REFPGA_IRQ_MAX_INTRS;

	chip->ngpio = value;

	/* make all of them till gpio count */
	for (i = 0; i < chip->ngpio; i++) {
		group = REFPGA_IRQ_GPIO_TO_GROUP(i);
		count = REFPGA_IRQ_GPIO_TO_IRQBIT(i);
		chip->irq_group[group].start = 0;
		chip->irq_group[group].count = (count + 1);
		chip->grpmask |= BIT(group);
		chip->irq_group[group].val = 0;
		chip->irq_group[group].mask = 0;
	}

	/*
	 * poll-interval - on boards that doesn't support interrupts
	 * Default poll interval is 1000 msec
	 */
	err = of_property_read_u32(dev->of_node, "poll-interval", &value);
	if (err)
		value = 5000;
	chip->poll_interval = value;

	return 0;
}

static int jnx_refpga_irq_probe(struct platform_device *pdev)
{
	struct refpga_irq_chip *chip;
	int err = 0;
	struct device *dev = &pdev->dev;

	if (!of_find_property(dev->of_node, "interrupt-controller", NULL))
    	return -ENODEV;

	chip = devm_kzalloc(dev, sizeof(*chip), GFP_KERNEL);
	if (!chip)
		return -ENOMEM;

	chip->base = tmc_membase;

	err = refpga_irq_of_init(dev, chip);
	if (err)
		return err;

	chip->dev = dev;
	chip->irq = platform_get_irq(pdev, 0);

	mutex_init(&chip->irq_lock);
	mutex_init(&chip->work_lock);

	refpga_irq_chip_init(chip);
	refpga_irq_gpio_setup(chip);

	err = refpga_irq_setup(dev, chip);
	if (err < 0)
		return err;

	if (of_find_property(dev->of_node, "gpio-controller", NULL)) {
		err = gpiochip_add(&chip->gpio);
		if (err) {
			dev_err(dev, "Failed to register REFPGA irq gpio : %d\n", err);
			goto err_teardown;
		}
	}

	refpga->irq = chip;
	dev_info(dev, "REFPGA IRQ registered: gpiobase: %d\n", chip->gpio.base);

	return 0;

err_teardown:
	if (chip->domain)
		refpga_irq_teardown(dev, chip);

	return err;
}

static int jnx_refpga_tmc_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct resource *res;
	int ret = 0;

	res = platform_get_resource(pdev, IORESOURCE_MEM, 0);
	if (!res) {
		dev_err(dev, "resource allocation failed\n");
		return -ENODEV;
	}

	tmc_membase = devm_ioremap(dev, res->start, resource_size(res));
	if (!tmc_membase) {
		dev_err(dev, "ioremap failed\n");
		return -ENOMEM;
	}

	refpga = devm_kzalloc(dev, sizeof(*refpga), GFP_KERNEL);
	if (!refpga) {
		dev_err(dev, "refpga memory allocation failed\n");
		return -ENOMEM;
	}

	reset_fan_full_speed(dev);

	ret = jnx_refpga_led_probe(pdev);
	if (ret != 0) {
		dev_err(dev, "Refpga LED probe failed\n");
		return ret;
	}

	dev_info(dev, "Refpga LED probe successful: TMC memoy base: %p\n",
					tmc_membase);

	ret = jnx_refpga_irq_probe(pdev);
	if (ret != 0) {
		dev_err(dev, "Refpga IRQ probe failed\n");
		return ret;
	}
	dev_info(dev, "Refpga IRQ probe successful: TMC memory base: %p\n",
				tmc_membase);

	platform_set_drvdata(pdev, refpga);

	return 0;
}

static int jnx_refpga_irq_remove(struct platform_device *pdev)
{
	struct refpga_chip *drv_data = platform_get_drvdata(pdev);
	struct refpga_irq_chip *chip = drv_data->irq;
	struct device *dev = &pdev->dev;

	cancel_delayed_work_sync(&chip->work);
	if (chip->domain)
		refpga_irq_teardown(dev, chip);
	gpiochip_remove(&chip->gpio);

	return 0;
}

static int jnx_refpga_tmc_remove(struct platform_device *pdev)
{
	jnx_refpga_led_remove(pdev);

	jnx_refpga_irq_remove(pdev);

	return 0;
}

static const struct of_device_id jnx_refpga_tmc_match[] = {
	{ .compatible = "jnx,refpga-tmc", },
	{ },
};
MODULE_DEVICE_TABLE(of, jnx_refpga_tmc_match);

static struct platform_driver jnx_refpga_tmc_driver = {
	.driver = {
		.name  = "refpga-tmc",
		.of_match_table = jnx_refpga_tmc_match,
	},
	.probe = jnx_refpga_tmc_probe,
	.remove = jnx_refpga_tmc_remove,
};

module_platform_driver(jnx_refpga_tmc_driver);

MODULE_DESCRIPTION("Juniper Networks REFPGA / TMC driver");
MODULE_AUTHOR("Ciju Rajan K <crajank@juniper.net>");
MODULE_LICENSE("GPL");
