/*
 * Juniper Garnet Fan CPLD driver
 *
 * drivers/mfd/jnx-garnet-fancpld.c
 *
 * This driver is being adpoted from Altera Fan CPLD mfd driver.
 *
 * Copyright (c) 2023, Juniper Networks
 * Author: Rahul Mishra (mishrar@juniper.net)
 *
 * Garnet Fan CPLD core MFD driver for Accton hardware.
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


#include <linux/module.h>
#include <linux/bug.h>
#include <linux/err.h>
#include <linux/i2c.h>
#include <linux/version.h>
#include <linux/kernel.h>
#include <linux/mfd/core.h>
#include <linux/of.h>
#include <linux/of_platform.h>
#include <linux/regmap.h>
#include <linux/slab.h>
#include <linux/hwmon.h>
#include <linux/hwmon-sysfs.h>
#include <linux/hwmon-vid.h>
#include "qfx5241-jnx-garnet-fancpld.h"

struct garnet_fan_data {
        struct i2c_client *client;
        struct regmap *regmap;
        struct device *hwmon_dev;
        int num_fans;   /* Number of fans */
        int factor;     /* fan speed/tach multiplication factor */
};

struct fan_presence_platform_data {
    u8 gpio_count;
    u8 fan_presence_reg;
};

static struct fan_presence_platform_data fan_presence_data = {
    .gpio_count = 32,
    .fan_presence_reg = 0x07,
};

struct led_pattern {
    u8 offset;
    u8 pattern_color[2];
    const char *name;
};

static struct led_pattern fan_leds[] = {
    { 0x6, { 0x40, 0x40 }, "fan3-status-fail" },
    { 0x6, { 0x80, 0x80 }, "fan3-status-ok"   },
    { 0x6, { 0x10, 0x10 }, "fan2-status-fail" },
    { 0x6, { 0x20, 0x20 }, "fan2-status-ok"   },
    { 0x6, { 0x04, 0x04 }, "fan1-status-fail" },
    { 0x6, { 0x08, 0x08 }, "fan1-status-ok"   },
    { 0x6, { 0x01, 0x01 }, "fan0-status-fail" },
    { 0x6, { 0x02, 0x02 }, "fan0-status-ok"   },
};

struct leds_platform_data {
    struct led_pattern *patterns;
    int num_patterns;
};

static struct leds_platform_data leds_data = {
    .patterns = fan_leds,
    .num_patterns = ARRAY_SIZE(fan_leds),
};

static struct mfd_cell fancpld_cells[] = {
    {
        .name = "s32afc-fan-presence",
        .id = 0,
        .platform_data = &fan_presence_data,
        .pdata_size = sizeof(fan_presence_data),
    },
    {
        .name = "leds-i2cs",
        .id = 0,
        .platform_data = &leds_data,
        .pdata_size = sizeof(leds_data),
    },
};

/* Converts a PWM register value to duty cycle.
 * Range:[GARNET_FAN_MODULE_DUTY_CYCLE_MIN - GARNET_FAN_MODULE_DUTY_CYCLE_MAX]
 * Returns - duty cycle.
 */
static int convert_pwm_reg_to_duty_cycle(int reg_val)
{
        int dividend;
        int divisor;
        int duty_cycle;

        reg_val &= GARNET_FAN_MODULE_PWM_MASK;
        /* duty_cycle =
         *(reg_val * 100) / (GARNET_FAN_MODULE_PWM_MASK);
         */
        dividend = (reg_val * 100);
        divisor = (GARNET_FAN_MODULE_PWM_MASK);
        duty_cycle = DIV_ROUND_CLOSEST(dividend, divisor);

        if (duty_cycle < GARNET_FAN_MODULE_DUTY_CYCLE_MIN)
                duty_cycle = GARNET_FAN_MODULE_DUTY_CYCLE_MIN;
        else if (duty_cycle > GARNET_FAN_MODULE_DUTY_CYCLE_MAX)
                duty_cycle = GARNET_FAN_MODULE_DUTY_CYCLE_MAX;

        return duty_cycle;
}

/* Some driver outputs a range of [0-255] as the PWM value.
 * This function converts the PWM register value to fit the scale of [0-255].
 * Returns - PWM. Range: [0 - GARNET_FAN_MODULE_PWM_MAX]
 */
static int convert_pwm_reg_to_pwm(int reg_val)
{
        int duty_cycle;
        int dividend;
        int divisor;
        int pwm;

        duty_cycle = convert_pwm_reg_to_duty_cycle(reg_val);

        /* slope = (GARNET_FAN_MODULE_PWM_MAX - 0) /            \
         *              (GARNET_FAN_MODULE_DUTY_CYCLE_MAX - 0)
         * pwm = duty_cycle * slope
         * pwm = (duty_cycle * GARNET_FAN_MODULE_PWM_MAX) / 100
         */
        dividend = (duty_cycle * GARNET_FAN_MODULE_PWM_MAX);
        divisor = GARNET_FAN_MODULE_DUTY_CYCLE_MAX;
        pwm = DIV_ROUND_CLOSEST(dividend, divisor);

        if (pwm < GARNET_FAN_MODULE_PWM_MIN)
                pwm = GARNET_FAN_MODULE_PWM_MIN;
        else if (pwm > GARNET_FAN_MODULE_PWM_MAX)
                pwm = GARNET_FAN_MODULE_PWM_MAX;

        return pwm;
}

/* Converts duty cycle to pwm register value. This method does NOT do error
 * check on input. If the caller calls with out-of-bound args, those will be
 * clamped to bounded range.
 * Returns - Value in register corresponding to the duty cycle.
 */
static int convert_duty_cycle_to_pwm_reg(int duty_cycle)
{
        int dividend;
        int divisor;
        int reg_val;

        if (duty_cycle < GARNET_FAN_MODULE_DUTY_CYCLE_MIN)
                duty_cycle = GARNET_FAN_MODULE_DUTY_CYCLE_MIN;
        if (duty_cycle > GARNET_FAN_MODULE_DUTY_CYCLE_MAX)
                duty_cycle = GARNET_FAN_MODULE_DUTY_CYCLE_MAX;

        /* reg_val = ((duty_cycle *
         *              (GARNET_FAN_MODULE_PWM_MASK))/100);
         */
        dividend = duty_cycle * (GARNET_FAN_MODULE_PWM_MASK);
        divisor = 100;

        reg_val = DIV_ROUND_CLOSEST(dividend, divisor);
        reg_val &= GARNET_FAN_MODULE_PWM_MASK;

        return reg_val;

}

/* Converts PWM to pwm reg value. This method does NOT do error
 * check on input. If the caller calls with out-of-bound args, those will be
 * clamped to bounded range.
 * Returns - Value in register corresponding to the PWM.
 */
static int convert_pwm_to_pwm_reg(int pwm)
{
        int duty_cycle;
        int dividend;
        int divisor;
        int reg_val;

        if (pwm < GARNET_FAN_MODULE_PWM_MIN)
                pwm = GARNET_FAN_MODULE_PWM_MIN;
        else if (pwm > GARNET_FAN_MODULE_PWM_MAX)
                pwm = GARNET_FAN_MODULE_PWM_MAX;

        /*
         * duty_cycle = (pwm * 100) / GARNET_FAN_MODULE_PWM_MAX
         */
        dividend = pwm * 100;
        divisor = GARNET_FAN_MODULE_PWM_MAX;
        duty_cycle = DIV_ROUND_CLOSEST(dividend, divisor);

        reg_val = convert_duty_cycle_to_pwm_reg(duty_cycle);

        return reg_val;
}

static int garnet_fan_read_reg(struct garnet_fan_data *data, u8 reg)
{
        unsigned int value;
        int ret;

        ret = regmap_read(data->regmap, reg, &value);
        if (ret < 0)
                goto done;
        ret = value;

done:
        return ret;
}

static int garnet_fan_write_reg(struct garnet_fan_data *data, u8 reg,
                                unsigned int value)
{
        int ret;

        ret = regmap_write(data->regmap, reg, value);

        return ret;
}

static int garnet_print_cpld_version(struct garnet_fan_data *data)
{
        struct i2c_client *client = data->client;
        struct device *dev = &client->dev;
        int ret;
        int board_id;
        int version_id;
        int cpld_major_version;
        int cpld_minor_version;

        ret = garnet_fan_read_reg(data, GARNET_BOARD_INFO_REG);
        if (ret < 0) {
                dev_err(dev, "Garnet Fan CPLD Board version read failed\n");
                return ret;
        }

        board_id = ret & GARNET_BOARD_ID_MASK;
        version_id = ret & GARNET_BOARD_VERSION_ID_MASK;

        ret = garnet_fan_read_reg(data, GARNET_CPLD_MAJOR_VER_REG);
        if (ret < 0) {
                dev_err(dev, "Garnet Fan CPLD major version read failed\n");
                return ret;
        }
        cpld_major_version = ret;

        ret = garnet_fan_read_reg(data, GARNET_CPLD_MINOR_VER_REG);
        if (ret < 0) {
                dev_err(dev, "Garnet Fan CPLD minor version read failed\n");
                return ret;
        }
        cpld_minor_version = ret;

        dev_info(dev, "Garnet FanCPLD BoardID is 0x%01X VersionID is 0x%01X\n",
                board_id, version_id);

        dev_info(dev, "Garnet FanCPLD Major-version 0x%X Minor-version 0x%X\n",
                cpld_major_version, cpld_minor_version);

        return ret;

}

static ssize_t garnet_fan_set_pwm(struct device *dev,
                                struct device_attribute *da,
                                const char *buf, size_t count)
{
        struct sensor_device_attribute_2 *attr = to_sensor_dev_attr_2(da);
        struct garnet_fan_data *data = dev_get_drvdata(dev);
        unsigned int pwm;
        int ret;
        int reg_val;

        if (kstrtouint(buf, 10, &pwm) < 0)
                return -EINVAL;

        if (pwm > GARNET_FAN_MODULE_PWM_MAX)
                return -EINVAL;

        reg_val = convert_pwm_to_pwm_reg(pwm);

        ret = garnet_fan_write_reg(data, attr->nr, reg_val);

        return ret ? ret : count;
}

static ssize_t garnet_fan_show_pwm(struct device *dev,
                                struct device_attribute *da, char *buf)
{
        struct sensor_device_attribute_2 *attr = to_sensor_dev_attr_2(da);
        struct garnet_fan_data *data = dev_get_drvdata(dev);
        int ret;

        ret = garnet_fan_read_reg(data, attr->nr);
        if (ret < 0)
                return ret;

        ret = convert_pwm_reg_to_pwm(ret);

        return snprintf(buf, PAGE_SIZE, "%d\n", ret);
}

static ssize_t garnet_fan_led_show(struct device *dev,
                            struct device_attribute *devattr,
                            char *buf)
{
    struct sensor_device_attribute_2 *attr = to_sensor_dev_attr_2(devattr);
    struct garnet_fan_data *data = dev_get_drvdata(dev);
    int fan = attr->index;  // Fan index: 1, 2, 3
    int reg_val;
    int ret;

    if (fan < 1 || fan > 4)
        return -EINVAL;

    ret = garnet_fan_read_reg(data, attr->nr);
    if (ret < 0)
        return ret;

    reg_val = ret;

    int red_bit = (fan - 1) * 2;
    int green_bit = red_bit + 1;

    bool red = !(reg_val & (1 << red_bit));
    bool green = !(reg_val & (1 << green_bit));

    const char *status;

    if (red && green)
        status = "amber\n";
    else if (red)
        status = "red\n";
    else if (green)
        status = "green\n";
    else
        status = "off\n";

    return snprintf(buf, PAGE_SIZE, "%s", status);
}


static ssize_t garnet_fan_show(struct device *dev, struct device_attribute *da,
                                char *buf)
{
        struct sensor_device_attribute_2 *attr = to_sensor_dev_attr_2(da);
        struct garnet_fan_data *data = dev_get_drvdata(dev);
        int ret;

        ret = garnet_fan_read_reg(data, attr->nr);
        if (ret < 0)
                return ret;

        /* As per datasheet, multiply Tach value read with the Tach factor */
        return snprintf(buf, PAGE_SIZE, "%d\n", ret * data->factor);
}

static umode_t garnet_fan_is_visible(struct kobject *kobj, struct attribute *a,
                                int n)
{
        struct device *dev = container_of(kobj, struct device, kobj);
        struct garnet_fan_data *data = dev_get_drvdata(dev);
        unsigned int index = n % GARNET_FAN_MAX_NUM;

        if (index < data->num_fans)
                return a->mode;

        return 0;
}


/* Fan speeds */
static SENSOR_DEVICE_ATTR_2(fan1_input,  S_IRUGO, garnet_fan_show, NULL,
                            GARNET_FAN_4_TACH_F, 1);
static SENSOR_DEVICE_ATTR_2(fan2_input,  S_IRUGO, garnet_fan_show, NULL,
                            GARNET_FAN_4_TACH_B, 2);
static SENSOR_DEVICE_ATTR_2(fan3_input,  S_IRUGO, garnet_fan_show, NULL,
                            GARNET_FAN_3_TACH_F, 3);
static SENSOR_DEVICE_ATTR_2(fan4_input,  S_IRUGO, garnet_fan_show, NULL,
                            GARNET_FAN_3_TACH_B, 4);
static SENSOR_DEVICE_ATTR_2(fan5_input,  S_IRUGO, garnet_fan_show, NULL,
                            GARNET_FAN_2_TACH_F, 5);
static SENSOR_DEVICE_ATTR_2(fan6_input,  S_IRUGO, garnet_fan_show, NULL,
                            GARNET_FAN_2_TACH_B, 6);
static SENSOR_DEVICE_ATTR_2(fan7_input,  S_IRUGO, garnet_fan_show, NULL,
                            GARNET_FAN_1_TACH_F, 7);
static SENSOR_DEVICE_ATTR_2(fan8_input,  S_IRUGO, garnet_fan_show, NULL,
                            GARNET_FAN_1_TACH_B, 8);


/* PWM values */
static SENSOR_DEVICE_ATTR_2(pwm1, S_IWUSR | S_IRUGO, garnet_fan_show_pwm,
                          garnet_fan_set_pwm, GARNET_FAN_4_PWM_F, 1);
static SENSOR_DEVICE_ATTR_2(pwm2, S_IWUSR | S_IRUGO, garnet_fan_show_pwm,
                          garnet_fan_set_pwm, GARNET_FAN_4_PWM_B, 2);
static SENSOR_DEVICE_ATTR_2(pwm3, S_IWUSR | S_IRUGO, garnet_fan_show_pwm,
                          garnet_fan_set_pwm, GARNET_FAN_3_PWM_F, 3);
static SENSOR_DEVICE_ATTR_2(pwm4, S_IWUSR | S_IRUGO, garnet_fan_show_pwm,
                          garnet_fan_set_pwm, GARNET_FAN_3_PWM_B, 4);
static SENSOR_DEVICE_ATTR_2(pwm5, S_IWUSR | S_IRUGO, garnet_fan_show_pwm,
                          garnet_fan_set_pwm, GARNET_FAN_2_PWM_F, 5);
static SENSOR_DEVICE_ATTR_2(pwm6, S_IWUSR | S_IRUGO, garnet_fan_show_pwm,
                          garnet_fan_set_pwm, GARNET_FAN_2_PWM_B, 6);
static SENSOR_DEVICE_ATTR_2(pwm7, S_IWUSR | S_IRUGO, garnet_fan_show_pwm,
                          garnet_fan_set_pwm, GARNET_FAN_1_PWM_F, 7);
static SENSOR_DEVICE_ATTR_2(pwm8, S_IWUSR | S_IRUGO, garnet_fan_show_pwm,
                          garnet_fan_set_pwm, GARNET_FAN_1_PWM_B, 8);

/* FAN LED */
static SENSOR_DEVICE_ATTR_2(fan1_led,  S_IRUGO, garnet_fan_led_show, NULL,
                            GARNET_FAN_LED, 1);
static SENSOR_DEVICE_ATTR_2(fan2_led,  S_IRUGO, garnet_fan_led_show, NULL,
                            GARNET_FAN_LED, 2);
static SENSOR_DEVICE_ATTR_2(fan3_led,  S_IRUGO, garnet_fan_led_show, NULL,
                            GARNET_FAN_LED, 3);
static SENSOR_DEVICE_ATTR_2(fan4_led,  S_IRUGO, garnet_fan_led_show, NULL,
                            GARNET_FAN_LED, 4);

static struct attribute *garnet_fan_attrs[] = {
        &sensor_dev_attr_fan1_input.dev_attr.attr,
        &sensor_dev_attr_fan2_input.dev_attr.attr,
        &sensor_dev_attr_fan3_input.dev_attr.attr,
        &sensor_dev_attr_fan4_input.dev_attr.attr,
        &sensor_dev_attr_fan5_input.dev_attr.attr,
        &sensor_dev_attr_fan6_input.dev_attr.attr,
        &sensor_dev_attr_fan7_input.dev_attr.attr,
        &sensor_dev_attr_fan8_input.dev_attr.attr,
        &sensor_dev_attr_pwm1.dev_attr.attr,
        &sensor_dev_attr_pwm2.dev_attr.attr,
        &sensor_dev_attr_pwm3.dev_attr.attr,
        &sensor_dev_attr_pwm4.dev_attr.attr,
        &sensor_dev_attr_pwm5.dev_attr.attr,
        &sensor_dev_attr_pwm6.dev_attr.attr,
        &sensor_dev_attr_pwm7.dev_attr.attr,
        &sensor_dev_attr_pwm8.dev_attr.attr,
        &sensor_dev_attr_fan1_led.dev_attr.attr,
        &sensor_dev_attr_fan2_led.dev_attr.attr,
        &sensor_dev_attr_fan3_led.dev_attr.attr,
        &sensor_dev_attr_fan4_led.dev_attr.attr,
        NULL,
};

static const struct attribute_group garnet_fan_group = {
        .attrs = garnet_fan_attrs,
        .is_visible = garnet_fan_is_visible,
};
__ATTRIBUTE_GROUPS(garnet_fan);


static struct regmap_config jnx_garnet_core_regmap_config = {
        .reg_bits = 8,
        .val_bits = 8,
        .max_register = MAX_REGMAP_REG,
        .cache_type = REGCACHE_NONE,
};


static int jnx_garnet_fancpld_core_probe(struct i2c_client *i2c
#if LINUX_VERSION_CODE < KERNEL_VERSION(6, 6, 0)
                          , const struct i2c_device_id *id
#endif
                          )
{
        struct device *dev = &i2c->dev;

#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 6, 0)
        const struct i2c_device_id *id = i2c_client_get_device_id(i2c);
#endif
        struct device_node *child;
        struct device_node *np = dev->of_node;
        struct regmap *regmap;
        int ret, ver, ncells;
        struct mfd_cell *cells;
        struct garnet_fan_data *data;


        data = devm_kzalloc(dev, sizeof(struct garnet_fan_data), GFP_KERNEL);
        if (!data)
                return -ENOMEM;

        regmap = devm_regmap_init_i2c(i2c, &jnx_garnet_core_regmap_config);
        if (IS_ERR(regmap)) {
                dev_err(dev, "failed to initialize regmap\n");
                return PTR_ERR(regmap);
        }

        data->regmap = regmap;

        ret = regmap_read(regmap, GARNET_CPLD_MAJOR_VER_REG, &ver);
        if (ret) {
                dev_err(dev, "failed to read the Garnet CPLD version\n");
                return ret;
        }

        data->num_fans = GARNET_FAN_MAX_NUM;
        data->factor = GARNET_FAN_TACH_FACTOR;

        /* Finalize the data from Device Tree if present */
        if (dev->of_node) {
                of_property_read_u32(dev->of_node,
                                     "num-fans", &data->num_fans);
                of_property_read_u32(dev->of_node,
                                     "tach-factor", &data->factor);
        }

        i2c_set_clientdata(i2c, data);
        data->client = i2c;

        data->hwmon_dev = devm_hwmon_device_register_with_groups(dev,
                                                        "qfx_fan", data,
                                                        garnet_fan_groups);

        ret = garnet_print_cpld_version(data);
        if (ret < 0)
                return ret;

        if (np) {
                ncells = of_get_child_count(np);
                dev_err(dev, "No child specified for %d\n", ncells);
                if (ncells == 0) {
                        dev_err(dev, "No child specified for %s\n", np->name);
                        return -EINVAL;
                }
                dev_err(dev, "child specified for %s\n", np->name);
                cells = devm_kzalloc(dev, ncells * sizeof(*cells), GFP_KERNEL);
                if (!cells)
                        return -ENOMEM;

                ncells = 0;
                for_each_available_child_of_node(dev->of_node, child) {
                        const char *s;
                        s = of_get_property(child, "compatible", NULL);
                        dev_err(dev, "child name:  %s\n", child->name);
                        if (!s) {
                                dev_err(dev,
                                        "Missing compatible property for %s\n",
                                        child->name);
                                return -EINVAL;
                        }
                        dev_err(dev, "of_property: %s\n", s);
                        dev_err(dev, "child name1:  %s\n", child->name);
                        cells[ncells].name = child->name;
                        cells[ncells].of_compatible = s;
                        ncells++;
                }
                if (ncells == 0) {
                        dev_err(dev, "No active child for %s\n", np->name);
                        return -EINVAL;
                }
        }
        ret = devm_mfd_add_devices(dev, i2c_adapter_id(i2c->adapter), 
                        fancpld_cells, ARRAY_SIZE(fancpld_cells), NULL, 0, NULL);
        return ret;

}

static void jnx_garnet_fancpld_core_remove(struct i2c_client *i2c)
{
        /* All resources taken during probe are device managed (devm_).
         * No explicit release required.
         */
}

static const struct of_device_id jnx_garnet_core_of_match[] = {
	{ .compatible = "jnpr,garnet-fancpld" },
	{ }
};
MODULE_DEVICE_TABLE(of, jnx_garnet_core_of_match);

static const struct i2c_device_id jnx_garnet_core_id[] = {
        { "garnet-fancpld", 0 },
        { }
};
MODULE_DEVICE_TABLE(i2c, jnx_garnet_core_id);

static struct i2c_driver jnx_garnet_core_driver = {
        .driver = {
                .name = "garnet-fancpld",
                .owner = THIS_MODULE,
                .of_match_table = of_match_ptr(jnx_garnet_core_of_match),
        },
        .probe    = jnx_garnet_fancpld_core_probe,
        .remove   = jnx_garnet_fancpld_core_remove,
        .id_table = jnx_garnet_core_id,
};

module_i2c_driver(jnx_garnet_core_driver);

MODULE_DESCRIPTION("Juniper Garnet Fan CPLD core MFD driver");
MODULE_AUTHOR("Rahul Mishra");
MODULE_LICENSE("GPL");
