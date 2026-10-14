/*
 * Juniper Networks I2CS FPGA LEDs driver
 *
 * Copyright (C) 2016 Juniper Networks
 * Author: Georgi Vlaev <gvlaev@juniper.net>
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 */

#include <linux/module.h>
#include <linux/regmap.h>
#include <linux/of.h>
#include <linux/delay.h>
#include <linux/leds.h>
#include <linux/i2c.h>
#include <linux/platform_device.h>
#include <linux/version.h>
#include "jnx-i2cs-core.h"
#include "jnx-wq.h"

#define FRU_LEDS        8 /* Total LEDs per register */
#define NUM_LEDS        128 /* Max number of FRU LEDs */
#define HW_BLINK_LEDS   3 /* LEDs with hw blink cap (standby not supported) */

/*
 * I2CS fru_led [0x12]
 *
 * bit 6   | bit 5    | bit 4   |...                        | bit 0
 * blink_ok|blink_fail|blink_act|led_standby|led_ok|led_fail|led_act
 */

/* TODO: Use the regmap from the parent MFD */
static struct regmap_config i2cs_leds_regmap_config = {
        .reg_bits = 8,
        .val_bits = 8,
        .max_register = I2CS_MAX_REGISTER,
};

struct i2cs_led {
        struct led_classdev lc;
        struct regmap *regmap;
        struct work_struct work;
        int blink;
        int on;
        int bit;
        u8  reg;
        u8  pattcolor;
        u8  pattcolor_mask;
};

struct i2cs_led_data {
        int num_leds;
        struct i2cs_led *leds;
};

struct led_patterns {
    u8 offset;
    u8 pattern_color[2];
    const char *name;
};

struct leds_platform_data {
    struct led_patterns *patterns;
    int num_patterns;
};

static void jnx_i2cs_leds_work(struct work_struct *work)
{
        struct i2cs_led *led = container_of(work, struct i2cs_led, work);
        int mask, value;
        
        if(led->reg) {
                if(led->pattcolor_mask) {
                        value = led->on ? 0 : led->pattcolor;
                        pr_info("LED %s: reg=0x%x mask=0x%x value=0x%x\n", led->lc.name, led->reg, led->pattcolor_mask, value);
                        regmap_update_bits(led->regmap, led->reg,
                                           led->pattcolor_mask, value & 0xff);
                }
                else {
                        mask = BIT(led->bit);
                        value = led->on << led->bit;
                        regmap_update_bits(led->regmap, led->reg, mask,
                                           value & 0xff);
                }
        } else {
                mask = (BIT(led->bit) << 4) | BIT(led->bit);
                value = ((led->blink << led->bit) << 4) | (led->on << led->bit);
                regmap_update_bits(led->regmap, I2CS_FRU_LED, mask, value & 0x7f);
        }
}

static void jnx_i2cs_leds_brightness_set(struct led_classdev *lc,
                                 enum led_brightness brightness)
{
        struct i2cs_led *led = container_of(lc, struct i2cs_led, lc);
        led->on = (brightness != LED_OFF);
        led->blink = 0; /* always turn off hw blink on brightness_set() */
        jnx_schedule_work(&led->work);
}

static int jnx_i2cs_leds_blink_set(struct led_classdev *lc,
                                   unsigned long *delay_on,
                                   unsigned long *delay_off)
{
        struct i2cs_led *led = container_of(lc, struct i2cs_led, lc);

        led->blink = (*delay_on > 0);
        led->on = led->blink; /* 'on' bit should be set if blinking */
        jnx_schedule_work(&led->work);

        return 0;
}


static int jnx_i2cs_leds_init_one(struct device *dev, struct device_node *np,
                                  struct i2cs_led_data *ild,
                                  struct regmap *regmap, int num)
{
        struct i2cs_led *led;
        const char *string;
        bool hw_blink;
        int ret, len;
        u32 reg;
        const __be32 *pattcolor;

        ret = of_property_read_u32(np, "reg", &reg);
        if (!ret && reg >= FRU_LEDS)
                return -EINVAL;

        pattcolor = of_get_property(np, "pattern-color", &len);
        if (pattcolor && (len != 2 * sizeof(u32)))
                return -EINVAL;

        if (ret && !pattcolor)
                return -ENODEV;

        led = &ild->leds[num];
        led->regmap = regmap;
        if(!ret)
                led->bit = reg;

        if(pattcolor) {
                led->pattcolor = be32_to_cpu(pattcolor[0]);
                led->pattcolor_mask = be32_to_cpu(pattcolor[1]);
        }

        if(!of_property_read_u32(np, "offset", &reg))
                led->reg = reg;

        if (!of_property_read_string(np, "label", &string))
                led->lc.name = string;
        else
                led->lc.name = np->name;

        if (!of_property_read_string(np, "linux,default-trigger", &string))
                led->lc.default_trigger = string;

        if(of_property_read_bool(np, "default-on"))
                led->lc.brightness = LED_FULL;
        else
                led->lc.brightness = LED_OFF;

        led->lc.brightness_set = jnx_i2cs_leds_brightness_set;
        if (led->bit <= HW_BLINK_LEDS) {
                hw_blink = of_property_read_bool(np, "hw-blink");
                if (hw_blink)
                        led->lc.blink_set = jnx_i2cs_leds_blink_set;
        }

        ret = devm_led_classdev_register(dev, &led->lc);
        if (ret)
                return ret;

        INIT_WORK(&led->work, jnx_i2cs_leds_work);

        return 0;
}

static int jnx_i2cs_leds_of_init(struct device *dev, struct i2cs_led_data *ild)
{
        struct device_node *child, *np = dev->of_node;
        struct regmap *regmap;
        struct i2c_client *client;
        int ret, num_leds;
        struct leds_platform_data *pdata = dev_get_platdata(dev);
        int i = 0;

        if (!dev->parent)
                return -ENODEV;

        client = i2c_verify_client(dev->parent);
        if (!client)
                return -ENODEV;

        regmap = devm_regmap_init_i2c(client, &i2cs_leds_regmap_config);
        if (IS_ERR(regmap)) {
                dev_err(dev, "Failed to allocate register map\n");
                return PTR_ERR(regmap);
        }
#ifdef QFX_SONIC
        num_leds = of_get_child_count(np);
        if (!num_leds || num_leds > NUM_LEDS)
                return -ENODEV;
#endif
        num_leds = pdata->num_patterns;

        ild->num_leds = num_leds;
        ild->leds = devm_kzalloc(dev, sizeof(struct i2cs_led) * num_leds,
                                 GFP_KERNEL);
        if (!ild->leds)
                return -ENOMEM;
#ifdef QFX_SONIC
        for_each_child_of_node(np, child) {
            ret = jnx_i2cs_leds_init_one(dev, child, ild, regmap, i++);
            if (ret)
                return ret;
        }
#endif
        for (i = 0; i < pdata->num_patterns; i++) {
            struct led_patterns *pattern = &pdata->patterns[i];
            dev_info(dev, "LED: %s offset=0x%x color0=0x%x color1=0x%x\n",
                     pattern->name, pattern->offset,
                     pattern->pattern_color[0], pattern->pattern_color[1]);
           
            ild->leds[i].reg = pattern->offset;
            ild->leds[i].pattcolor = pattern->pattern_color[0];
            ild->leds[i].pattcolor_mask = pattern->pattern_color[1];
            ild->leds[i].regmap = regmap;
            ild->leds[i].lc.name = pattern->name;
            ild->leds[i].lc.brightness_set = jnx_i2cs_leds_brightness_set;
            ild->leds[i].lc.brightness = LED_OFF;
            dev_info(dev, "LED: %s offset=0x%x color0=0x%x color1=0x%x\n",
                     ild->leds[i].lc.name, ild->leds[i].reg,
                     ild->leds[i].pattcolor, ild->leds[i].pattcolor_mask);
            ret = devm_led_classdev_register(dev, &ild->leds[i].lc);
            if (ret) {
                dev_info(dev, "Phani1 here");
                return ret;
            }
            dev_info(dev, "Phani2 here");
            INIT_WORK(&ild->leds[i].work, jnx_i2cs_leds_work);
        /* Initialize/register your LEDs here using the pattern data */
        /* e.g., allocate led_classdev, set up regmap writes, etc. */
        }

        return 0;
}

static int jnx_i2cs_leds_probe(struct platform_device *pdev)
{
        struct device *dev = &pdev->dev;
        struct i2cs_led_data *ild;
        int ret;

        ild = devm_kzalloc(dev, sizeof(*ild), GFP_KERNEL);
        if (!ild)
                return -ENOMEM;

        ret = jnx_i2cs_leds_of_init(dev, ild);
        if (ret < 0)
                return ret;
        platform_set_drvdata(pdev, ild);

        return 0;
}

#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 6, 0)
static void jnx_i2cs_leds_remove(struct platform_device *pdev)
#else
static int jnx_i2cs_leds_remove(struct platform_device *pdev)
#endif
{
        struct i2cs_led_data *ild = platform_get_drvdata(pdev);
        int i;

        for (i = 0; i < ild->num_leds; i++) {
                devm_led_classdev_unregister(&pdev->dev, &ild->leds[i].lc);
                cancel_work_sync(&ild->leds[i].work);
        }

#if LINUX_VERSION_CODE < KERNEL_VERSION(6, 6, 0)
        return 0;
#endif
}

static const struct of_device_id jnx_i2cs_leds_match[] = {
        { .compatible = "jnx,leds-i2cs", },
        { },
};
MODULE_DEVICE_TABLE(of, jnx_i2cs_leds_match);

static struct platform_driver jnx_i2cs_leds_driver = {
        .driver = {
                .name  = "leds-i2cs",
                .of_match_table = jnx_i2cs_leds_match,
        },
        .probe = jnx_i2cs_leds_probe,
        .remove = jnx_i2cs_leds_remove,
};

module_platform_driver(jnx_i2cs_leds_driver);

MODULE_DESCRIPTION("Juniper Networks I2CS leds driver");
MODULE_AUTHOR("Georgi Vlaev <gvlaev@juniper.net>");
MODULE_LICENSE("GPL");
