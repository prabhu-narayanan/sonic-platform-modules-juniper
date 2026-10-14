/*
 * Juniper Networks Accton fpga LEDs driver
 *
 * Copyright (C) 2023 Juniper Networks
 * Author: Diwanshu Bansal <diwanshub@juniper.net>
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
#include <linux/mfd/core.h>
#include <linux/platform_device.h>
#include <linux/io.h>
#include <linux/printk.h>
#include <linux/version.h>
#include "qfx5241-jnx-garnet.h"
#include "qfx5241-jnx-garnet64-core.h"
#include <linux/pci.h>
#include <linux/sched.h>

/*
 * We have three type of System LEDs - BeaconLed, SystemLed, AlarmLed.
 *
 * System LED Bit Set Values: control the System LEDs & their color states.
 *
 * - SYSTEM_LED_ON: Turns ON a System LED RGB component. The value is set
 *   to 0x80 for System LEDs by default to avoid bleeding issues.
 * - SYSTEM_LED_OFF: Turns OFF a System LED RGB component.
 *
 * For AMBER color on alarm LED:
 * - AMBER = RED + GREEN.
 * - SYSTEM_ALARM_LED_AMBER_R and SYSTEM_ALARM_LED_AMBER_G: Bit Set Values
 *   used to simulate the AMBER color by controlling the red and green
 *   components respectively.
 *
 * These values can be overridden via DTS for platform-specific control.
 */

#define SYSTEM_LED_ON                           0x80
#define SYSTEM_LED_OFF                          0x0
#define SYSTEM_ALARM_LED_AMBER_R                0x82
#define SYSTEM_ALARM_LED_AMBER_G                0x32

/* Number of Parameters supported by ledx_brightness */
#define PORT_LED_CTRL_SW_PORT_CMASK              0x3

/* Number of Parameters supported by ledx_brightness */
#define PORT_LED_CTRL_SW_SFP_PORT_CMASK  0x1
#define PORT_LED_CTRL_SW_SYSTEM_LED_CMASK        0x7

/* Mask to verify the input, pushed to the register */
#define PORT_LED_CTRL_SW_PORT_COLOR(c)    \
    ((c) & PORT_LED_CTRL_SW_PORT_CMASK)

/* Mask to verify the input, pushed to the register */
#define PORT_LED_CTRL_SW_SFP_PORT_COLOR(c)        \
    ((c) & PORT_LED_CTRL_SW_SFP_PORT_CMASK)

#define PORT_LED_CTRL_SW_SYSTEM_COLOR(c)          \
    ((c) & PORT_LED_CTRL_SW_SYSTEM_LED_CMASK)

#define PORT_LED_CTRL_SW_PORT_RED_VALUE(c) \
    (( (c) & 0x01 )  > 0 ? 0 : 1)

#define PORT_LED_CTRL_SW_PORT_GREEN_VALUE(c) \
    ((( (c) & 0x02 ) >> 1 ) > 0 ? 0 : 1)

#define PORT_LED_CTRL_SW_PORT_BLUE_VALUE(c) \
    ((( (c) & 0x03 ) >> 2 ) > 0 ? 0 : 1)

/* pushes the bit to the offset */
#define LED_CTRL_CLEAR_SET_OFFSET(c,led) \
    ( (c) = (c) << (led)->port_addr_offset) /* Inverts the value and make the offset 0 and then bitwise
                                               and the val to clear out*/
#define LED_CTRL_CLEAR_OFFSET_VALUE(val,c,led) \
    ( (val) = (val) & ~(LED_CTRL_CLEAR_SET_OFFSET(c,led)))

/* Maximum number of system led supported */
#define NUM_SYSTEM_LEDS 5

/* FPGA Register Write */
#define GARNET_FPGA_REG_SET(chip, reg, value, offset, reg_val)          \
    do {                                                            \
        offset = reg % 4;                                       \
        reg_val = ioread32(chip->addr + (reg - offset));        \
        reg_val &= ~(0xff << offset * 8);                       \
        reg_val |= (value << offset * 8);                       \
        iowrite32(reg_val, chip->addr + (reg - offset));        \
    } while (0);                                                    \

/* FPGA Bit Write */
#define GARNET_FPGA_BIT_SET(chip, reg, value, offset, reg_val)          \
    do {                                                            \
        reg_val = ioread32(chip->addr + reg);                   \
        reg_val &= ~(0x01 << offset);                           \
        reg_val |= value << offset;                             \
        iowrite32(reg_val, chip->addr + reg);                   \
    } while (0);                                            \

/* Custom Brightness enum for Port LED functionality */
enum ledx_brightness {
    LEDX_OFF                  = 0,
    LEDX_RED                  = 1,
    LEDX_GREEN                = 2,
    LEDX_AMBER                = 3,

};

/* Custom Brightness enum for Alarm LED functionality */
enum alarm_ledx_brightness {
    ALARM_LEDX_OFF            = 0,
    ALARM_LEDX_RED            = 1,
    ALARM_LEDX_GREEN          = 2,
    ALARM_LEDX_AMBER          = 3,
    ALARM_LEDX_RED_BLINK      = 4,
};

/* Custom Brightness enum for System LED functionality */
enum system_ledx_brightness {
    SYSTEM_LEDX_OFF            = 0,
    SYSTEM_LEDX_RED            = 1,
    SYSTEM_LEDX_GREEN          = 2,
    SYSTEM_LEDX_AMBER          = 3,
    SYSTEM_LEDX_GREEN_BLINK    = 4,
};

enum driver_category {
    System_Led              = 0,
    Port_Led                = 1,
    SFP_Led                 = 2,
};

enum system_led_category {
    Beacon_LED              = 0,
    System_LED              = 1,
    Alarm_LED               = 2,
};

struct garnet_led {
    struct led_classdev lc;
    struct work_struct work;
    void __iomem *addr;             /* pointer of the add*/

    enum ledx_brightness brightness;

    int port_id;                    /* port_id is identification for each led */
    int port_addr_offset;           /* bit offset for each led */

    u32 port_addr_green;            /* port led green register offset */
    u32 port_addr_red;              /* port led red register offset */
    u32 port_addr_blue;             /* port led blue register offset */

    u32 sfp_port_add;               /* sfp port led register offset */

    /* We have three type of System LEDs - BeaconLed, SystemLed, AlarmLed */

    enum system_led_category led_type; /* system led type */
    u32 system_addr_green;          /* system led green register offset */
    u32 system_addr_red;            /* system led red register offset */
    u32 system_addr_blue;           /* system led blue register offset */
    u32 blink_reg;                          /* system led blink reg */
    int blink_reg_offset;           /* system led blink offset */

    /* System LED bit set values (default or from DTS) */
    u32 system_led_on;     /* Bit set value to set system LED ON */
    u32 system_led_off;    /* Bit set value to set system LED OFF */
    u32 system_alarm_led_amber_r;   /* Bit set value for RED part of AMBER
                                     * alarm LED */
    u32 system_alarm_led_amber_g;   /* Bit set value for GREEN part of AMBER
                                     * alarm LED */

    int spi_busy_bit;
    struct garnet_fpga_data *pdriver_data;
    void __iomem *fpga_membase;
    u8 (*getreg) (struct garnet_led *led, u32 reg_addr);
    void (*setreg) (struct garnet_led *led, u32 reg_addr, u8 value);
};

struct garnet_led_data {
    int num_leds;
    struct garnet_led *leds;
};

static inline u8 garnet_led_reg_get_nolock(struct garnet_led *led, u32 reg_addr)
{
    return ioread8(led->addr + reg_addr);
}

static inline void garnet_led_reg_set_nolock(struct garnet_led *led, u32 reg_addr,
        u8 value)
{
    iowrite8(value, led->addr + reg_addr);
}

static inline u8 garnet_led_reg_get(struct garnet_led *led, u32 reg_addr)
{
    u8 value;
    struct garnet_fpga_data *pdriver_data = led->pdriver_data;

    mutex_lock(&pdriver_data->lock[led->spi_busy_bit]);
    CHECK_SPI_BUSY(led, led->spi_busy_bit);

    value = ioread8(led->addr + reg_addr);

    CHECK_SPI_BUSY(led, led->spi_busy_bit);
    mutex_unlock(&pdriver_data->lock[led->spi_busy_bit]);

    return value;
}

static inline void garnet_led_reg_set(struct garnet_led *led, u32 reg_addr,
        u8 value)
{
    struct garnet_fpga_data *pdriver_data = led->pdriver_data;

    mutex_lock(&pdriver_data->lock[led->spi_busy_bit]);
    CHECK_SPI_BUSY(led, led->spi_busy_bit);

    iowrite8(value, led->addr + reg_addr);

    CHECK_SPI_BUSY(led, led->spi_busy_bit);
    mutex_unlock(&pdriver_data->lock[led->spi_busy_bit]);
}
/* Setting the default values for each Port Led */
static void garnet_port_led_register_set(struct garnet_led *led)
{
    u8 value = 0x0;
    u8 to_set = 0x0;
    u8 clear_set = 0x01;
    struct garnet_fpga_data *pdriver_data = led->pdriver_data;

    /* Red LED set */
    to_set = led->brightness;
    value = led->getreg(led, led->port_addr_red);

    LED_CTRL_CLEAR_OFFSET_VALUE(value,clear_set,led);
    to_set = PORT_LED_CTRL_SW_PORT_RED_VALUE(to_set) << led->port_addr_offset;
    value = value | to_set;

    led->setreg(led, led->port_addr_red, 0);
    led->setreg(led, led->port_addr_red, value);

    // /* Green LED set */
    to_set = led->brightness;
    clear_set = 0x01;
    value = led->getreg(led, led->port_addr_green);

    LED_CTRL_CLEAR_OFFSET_VALUE(value,clear_set,led);
    to_set = PORT_LED_CTRL_SW_PORT_GREEN_VALUE(to_set) << led->port_addr_offset;
    value = value | to_set;

    led->setreg(led, led->port_addr_green, 0);
    led->setreg(led, led->port_addr_green, value);

    /* Blue LED set */
    to_set = led->brightness;
    clear_set = 0x01;
    value = led->getreg(led, led->port_addr_blue);

    LED_CTRL_CLEAR_OFFSET_VALUE(value,clear_set,led);
    to_set = PORT_LED_CTRL_SW_PORT_BLUE_VALUE(to_set) << led->port_addr_offset;
    value = value | to_set;
    led->setreg(led, led->port_addr_blue, 0);
    led->setreg(led, led->port_addr_blue, value);
}

static void garnet_sfp_port_led_register_set(struct garnet_led *led)
{
    u8 value = 0x0;
    u8 to_set = 0x0;
    u8 clear_set = 0x01;
    struct garnet_fpga_data *pdriver_data = led->pdriver_data;

    to_set = led->brightness > 0 ? 0 : 1;
    value = led->getreg(led, led->sfp_port_add);

    LED_CTRL_CLEAR_OFFSET_VALUE(value,clear_set,led);
    to_set = to_set << led->port_addr_offset;
    value = value | to_set;
    led->setreg(led, led->sfp_port_add, value);
}



static void garnet_system_led_register_set(struct garnet_led *led)
{
    u32 to_set = 0x0, clear_reg = 0x0;
    u32 bit_set = 0x01, bit_clear = 0x0;
    u32 reg_val = 0x0, offset = 0x0;

    GARNET_FPGA_REG_SET(led, led->system_addr_blue, clear_reg, offset,
            reg_val);
    GARNET_FPGA_REG_SET(led, led->system_addr_green, clear_reg, offset,
            reg_val);
    GARNET_FPGA_REG_SET(led, led->system_addr_red, clear_reg, offset,
            reg_val);
    GARNET_FPGA_BIT_SET(led, led->blink_reg, bit_clear, led->blink_reg_offset,
            reg_val);

    switch (led->led_type) {
        case Beacon_LED:
            bit_set = led->brightness > 0 ? 1 : 0;
            GARNET_FPGA_BIT_SET(led, led->blink_reg, bit_set,
                    led->blink_reg_offset, reg_val);

            to_set = led->brightness > 0 ?
                led->system_led_on : led->system_led_off;
            GARNET_FPGA_REG_SET(led, led->system_addr_blue,
                    to_set, offset, reg_val);
            break;
        case System_LED:
            to_set = led->brightness;
            switch(to_set) {
                case SYSTEM_LEDX_RED:
                    GARNET_FPGA_REG_SET(led, led->system_addr_red,
                            led->system_led_on, offset, reg_val);
                    break;
                case SYSTEM_LEDX_GREEN:
                    GARNET_FPGA_REG_SET(led, led->system_addr_green,
                            led->system_led_on, offset, reg_val);
                    break;
                case SYSTEM_LEDX_AMBER:
                    GARNET_FPGA_REG_SET(led, led->system_addr_red,
                            led->system_alarm_led_amber_r, offset, reg_val);
                    GARNET_FPGA_REG_SET(led, led->system_addr_green,
                            led->system_alarm_led_amber_g, offset, reg_val);
                    break;
                case SYSTEM_LEDX_GREEN_BLINK:
                    GARNET_FPGA_REG_SET(led, led->system_addr_green,
                            led->system_led_on, offset, reg_val);
                    GARNET_FPGA_BIT_SET(led, led->blink_reg, bit_set,
                            led->blink_reg_offset, reg_val);
                    break;
                default:
                    break;
            }
        case Alarm_LED:
            to_set = led->brightness;
            switch( to_set ) {
                case ALARM_LEDX_RED:
                    GARNET_FPGA_REG_SET(led, led->system_addr_red,
                            led->system_led_on, offset, reg_val);
                    break;
                case ALARM_LEDX_AMBER:
                    GARNET_FPGA_REG_SET(led, led->system_addr_red,
                            led->system_alarm_led_amber_r, offset, reg_val);
                    GARNET_FPGA_REG_SET(led, led->system_addr_green,
                            led->system_alarm_led_amber_g, offset, reg_val);
                    break;
                case ALARM_LEDX_GREEN:
                    GARNET_FPGA_REG_SET(led, led->system_addr_green,
                            led->system_led_on, offset, reg_val);
                    break;
                case ALARM_LEDX_RED_BLINK:
                    GARNET_FPGA_REG_SET(led, led->system_addr_red,
                            led->system_led_on, offset, reg_val);
                    GARNET_FPGA_BIT_SET(led, led->blink_reg, bit_set,
                            led->blink_reg_offset, reg_val);
                    break;
                default:
                    break;
            }
            break;
        default:
            break;
    }
}

static void jnx_garnet_port_leds_work(struct work_struct *work)
{
    struct garnet_led *led = container_of(work, struct garnet_led, work);
    garnet_port_led_register_set(led);
}

static void jnx_garnet_sfp_port_leds_work(struct work_struct *work)
{
    struct garnet_led *led = container_of(work, struct garnet_led, work);
    garnet_sfp_port_led_register_set(led);
}


static void jnx_garnet_system_leds_work(struct work_struct *work)
{
    struct garnet_led *led = container_of(work, struct garnet_led, work);
    garnet_system_led_register_set(led);
}

static void garnet_port_led_brightness_set(struct led_classdev *lc,
        enum led_brightness b)
{
    struct garnet_led *led = container_of(lc, struct garnet_led, lc);
    led->brightness = PORT_LED_CTRL_SW_PORT_COLOR(b);
    schedule_work(&led->work);
}

static void garnet_sfp_port_led_brightness_set(struct led_classdev *lc,
        enum led_brightness b)
{
    struct garnet_led *led = container_of(lc, struct garnet_led, lc);
    led->brightness = PORT_LED_CTRL_SW_SFP_PORT_COLOR(b);
    schedule_work(&led->work);
}


static void garnet_system_led_brightness_set(struct led_classdev *lc,
        enum led_brightness b)
{
    struct garnet_led *led = container_of(lc, struct garnet_led, lc);
    led->brightness = PORT_LED_CTRL_SW_SYSTEM_COLOR(b);
    schedule_work(&led->work);
}

static int jnx_garnet_port_leds_init(struct device *dev,
        struct garnet_port_led_platform_data* pdata, struct garnet_led *led,
        void __iomem *base)
{
    int ret;

    INIT_WORK(&led->work, jnx_garnet_port_leds_work);

    /* Initialize Default Values */
    garnet_port_led_register_set(led);

    ret = devm_led_classdev_register(dev, &led->lc);
    if (ret) {
        dev_err(dev, "Failed to register port led reg 0x%p\n",
                base);
        return ret;
    }
    return 0;
}

static int jnx_garnet_sfp_port_leds_init(struct device *dev,
        struct garnet_port_led_platform_data* pdata,
        struct garnet_led *led, void __iomem *base)
{
    int ret;

    INIT_WORK(&led->work, jnx_garnet_sfp_port_leds_work);

    /* Initialize Default Values */
    garnet_sfp_port_led_register_set(led);

    ret = devm_led_classdev_register(dev, &led->lc);
    if (ret) {
        dev_err(dev, "Failed to register port led reg 0x%p\n",
                base);
        return ret;
    }
    return 0;
}


static int jnx_garnet_system_leds_init(struct device *dev,
        struct garnet_system_led_platform_data *p_data,
        struct garnet_led *led, void __iomem *base)
{
    int ret;

    INIT_WORK(&led->work, jnx_garnet_system_leds_work);

    /* Initialize Default Values */
    garnet_system_led_register_set(led);
    dev_err(dev, "Registering class dev for %s\n",led->lc.name);

    ret = devm_led_classdev_register(dev, &led->lc);
    if (ret) {
        dev_err(dev, "Failed to register port led reg 0x%p\n",
                base);
        return ret;
    }
    return 0;

}

static int garnet_port_led_populate_details(struct port_led_config *port_led,
        int port_num, struct garnet_led *led, struct device *dev,
        void __iomem *base, int spi_busy_bit,
        struct garnet_fpga_data *pdriver_data)
{
    u32 red_led_reg, green_led_reg, blue_led_reg;
    int port_bit_offset = 0;
    int ret, def_color;
    char label[24], pre[24];

    led->port_id = port_num;

    if (pdriver_data->no_lock) {
        led->setreg = garnet_led_reg_set_nolock;
        led->getreg = garnet_led_reg_get_nolock;
    } else {
        led->setreg = garnet_led_reg_set;
        led->getreg = garnet_led_reg_get;
    }

    led->lc.name = port_led->label;

    def_color = 0; // OFF
    blue_led_reg = port_led->rgb_reg_base_offset;
    green_led_reg = port_led->rgb_reg_base_offset + 1;
    red_led_reg = port_led->rgb_reg_base_offset + 2;
    port_bit_offset = port_led->bit_offset;

    led->brightness = PORT_LED_CTRL_SW_PORT_COLOR(def_color); // 0: OFF
    led->port_addr_blue = blue_led_reg;
    led->port_addr_green = green_led_reg;
    led->port_addr_red = red_led_reg;
    led->port_addr_offset = port_bit_offset;
    led->addr = base;
    led->spi_busy_bit = spi_busy_bit;
    led->pdriver_data = pdriver_data;
    led->fpga_membase = pcim_iomap_table(pdriver_data->pdev)[0];

    led->lc.brightness = PORT_LED_CTRL_SW_PORT_COLOR(def_color);
    led->lc.brightness_set = garnet_port_led_brightness_set;

    return 0;
}

static int garnet_sfp_led_populate_details(struct port_led_config *port_led,
        int port_num, struct garnet_led *led, struct device *dev,
        void __iomem *base, int spi_busy_bit,
        struct garnet_fpga_data *pdriver_data)
{

    int bit_offset = 0;
    int ret = 0, def_color = 0;
    u32 port_add_sfp;
    char label[24], pre[24];

    led->port_id = port_num;

    if (pdriver_data->no_lock) {
        led->setreg = garnet_led_reg_set_nolock;
        led->getreg = garnet_led_reg_get_nolock;
    } else {
        led->setreg = garnet_led_reg_set;
        led->getreg = garnet_led_reg_get;
    }

    bit_offset = port_led->bit_offset;
    port_add_sfp = port_led->rgb_reg_base_offset;
    led->lc.name = port_led->label;

    led->brightness = PORT_LED_CTRL_SW_SFP_PORT_COLOR(def_color);
    led->sfp_port_add = port_add_sfp;
    led->port_addr_offset = bit_offset;
    led->addr = base;
    led->spi_busy_bit = spi_busy_bit;
    led->pdriver_data = pdriver_data;
    led->fpga_membase = pcim_iomap_table(pdriver_data->pdev)[0];

    led->lc.brightness = PORT_LED_CTRL_SW_SFP_PORT_COLOR(def_color);
    led->lc.brightness_set = garnet_sfp_port_led_brightness_set;

    return 0;
}



static int garnet_system_led_populate_details(struct device *dev,
        struct system_led_config *led_data,
        struct garnet_led *led,
        void __iomem *base)
{
    u32 read_offset = 0;
    u32 system_red_addr,system_blue_addr,system_green_addr;
    int ret, def_color;
    const char *string;

    u32 system_led_on;
    u32 system_led_off;
    u32 system_alarm_led_amber_r;
    u32 system_alarm_led_amber_g;

    u32 port_reg;
    int port_bit_offset;
    int type;

    system_led_on = SYSTEM_LED_ON;
    system_led_off = SYSTEM_LED_OFF;
    system_alarm_led_amber_r = SYSTEM_ALARM_LED_AMBER_R;
    system_alarm_led_amber_g = SYSTEM_ALARM_LED_AMBER_G;

    led->lc.name = led_data->name;
    led->led_type = led_data->led_type;
    led->system_addr_blue = led_data->rgb_reg_base_offset;
    led->system_addr_green = led_data->rgb_reg_base_offset + 1;
    led->system_addr_red = led_data->rgb_reg_base_offset + 2;
    led->blink_reg = led_data->blink_reg_offset;
    led->blink_reg_offset = led_data->blink_reg_bit_offset;
    led->addr = base;
    led->brightness = PORT_LED_CTRL_SW_SYSTEM_COLOR(def_color);

    led->lc.brightness = PORT_LED_CTRL_SW_SYSTEM_COLOR(def_color);
    led->lc.brightness_set = garnet_system_led_brightness_set;

    led->system_led_on = system_led_on;
    led->system_led_off = system_led_off;
    led->system_alarm_led_amber_r = system_alarm_led_amber_r;
    led->system_alarm_led_amber_g = system_alarm_led_amber_g;

    return 0;
}

static int jnx_garnet_leds_of_init(struct platform_device *pdev,struct device *dev,
        struct garnet_led_data *ild, struct resource *res)
{
    struct garnet_fpga_data *pdriver_data;
    void __iomem *addr;
    const struct platform_device_id *id;

    u32 category;
    u32 read_offset = 0;

    int num_args, num_ports, port_id = 0;
    int ret;
    int num_leds = 0, spi_busy_bit = 0;

    id = platform_get_device_id(pdev);
    if (!id) {
        dev_err(dev, "Couldn't fetch device id\n");
        return -ENODEV;
    }

    addr = devm_ioremap(dev, res->start, resource_size(res));
    if (!addr) {
        dev_err(dev, "ioremap failed\n");
        return -ENOMEM;
    }

    pdriver_data = (struct garnet_fpga_data *)(pdev->dev.parent->driver_data);

    if ((res->start % 0x10000) < 0x3000)
        spi_busy_bit = 0;
    else
        spi_busy_bit = 1;

    switch (id->driver_data) {
        case 0: { // SYSTEM LED
            struct garnet_system_led_platform_data *pdata =
                (struct garnet_system_led_platform_data *)dev_get_platdata(&pdev->dev);
            struct system_led_config *led;
            num_leds = pdata->num_leds;
            if (!num_leds || num_leds > NUM_SYSTEM_LEDS)
                return -ENODEV;

            ild->num_leds = num_leds;

            ild->leds = devm_kzalloc(dev,
                    sizeof(struct garnet_led)
                    * ild->num_leds, GFP_KERNEL);
            if (!ild->leds) {
                dev_err(dev, "SYSTEM_LED: space allocation failed\n");
                return -ENOMEM;
            }
            led = pdata->leds;
            for (int l = 0; l < num_leds; l++) {
                ret = garnet_system_led_populate_details(dev, led + l,
                        &ild->leds[port_id], addr);
                if (ret) {
                    dev_err(dev, "SYSTEM_LED: Error \
                            registering port leds \
                            details%d\n",
                            ret);
                    return ret;
                } else {
                    dev_err(dev, "SYSTEM_LED: Populated LED %d details\n", l);
                }

                ret = jnx_garnet_system_leds_init(dev, pdata, &ild->leds[port_id],
                        addr);
                if (ret) {
                    dev_err(dev, "SYSTEM_LED: Error \
                            Initializing system leds \
                            details%d\n",
                            ret);
                    return ret;
                }
                port_id++;
            }
            break;
            }
        case 1: // PORT LED
        case 2: {
            struct garnet_port_led_platform_data *pdata =
                (struct garnet_port_led_platform_data *)dev_get_platdata(&pdev->dev);
            struct port_led_config *led;
            num_ports = pdata->num_leds;
            ild->num_leds = num_ports;

            ild->leds = devm_kzalloc(dev,
                    sizeof(struct garnet_led)
                    * ild->num_leds, GFP_KERNEL);
            if (!ild->leds) {
                dev_err(dev, "PORT_LED: space allocation failed\n");
                return -ENOMEM;
            }
            led = pdata->leds;

            for (port_id = 0; port_id < num_ports; port_id++) {
                ret = garnet_port_led_populate_details(led + port_id, port_id,
                        &ild->leds[port_id], dev, addr, spi_busy_bit, pdriver_data);
                if (ret) {
                    dev_err(dev,
                            "PORT_LED: Error registering port leds details %d\n",
                            ret);
                    return ret;
                }

                ret = jnx_garnet_port_leds_init(dev, pdata, &ild->leds[port_id], addr);
                if (ret) {
                    dev_err(dev,
                            "PORT_LED: leds init failure %d\n", 
                            ret);
                    return ret;
                }
            }

            break;
            }
        case 3: {// SFP PORT LED
            struct garnet_port_led_platform_data *pdata =
                (struct garnet_port_led_platform_data *)dev_get_platdata(&pdev->dev);
            struct port_led_config *led;
            num_ports = pdata->num_leds;
            ild->num_leds = num_ports;

            ild->leds = devm_kzalloc(dev,
                    sizeof(struct garnet_led)
                    * ild->num_leds, GFP_KERNEL);
            if (!ild->leds) {
                dev_err(dev, "SFP_LED: space allocation failed\n");
                return -ENOMEM;
            }
            led = pdata->leds;

            for (port_id = 0; port_id < num_ports; port_id++) {
                ret = garnet_sfp_led_populate_details(led + port_id, port_id,
                        &ild->leds[port_id], dev, addr, spi_busy_bit, pdriver_data);
                if (ret) {
                    dev_err(dev,
                            "PORT_LED: Error registering port leds details %d\n",
                            ret);
                    return ret;
                }

                ret = jnx_garnet_sfp_port_leds_init(dev, pdata, &ild->leds[port_id], addr);
                if (ret) {
                    dev_err(dev,
                            "PORT_LED: leds init failure %d\n", 
                            ret);
                    return ret;
                }
            }
            break;
            }
        default:
            dev_warn(dev, "Unknown LED type\n");
            break;
    }

    return 0;
}

static int garnet_leds_probe(struct platform_device *pdev)
{
    struct device *dev = &pdev->dev;
    const struct platform_device_id *id;
    struct garnet_led_data *ild;
    int ret;
    struct resource *res;

    ild = devm_kzalloc(dev, sizeof(*ild), GFP_KERNEL);
    if (!ild) {
        dev_err(dev, "ild allocation failed\n");
        return -ENOMEM;
    }

    platform_set_drvdata(pdev, ild);

    res = platform_get_resource(pdev, IORESOURCE_MEM, 0);
    if (!res) {
        dev_err(dev, "res allocation failed\n");
        return -ENODEV;
    }

    ret = jnx_garnet_leds_of_init(pdev, dev, ild, res);
    if (ret < 0)
        return ret;

    return 0;
}

#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 6, 0)
static void garnet_leds_remove(struct platform_device *pdev)
#else
static int garnet_leds_remove(struct platform_device *pdev)
#endif
{
    struct garnet_led_data *ild = platform_get_drvdata(pdev);
    int i;

    for (i = 0; i < ild->num_leds; i++) {
        if(&ild->leds[i].lc)
            devm_led_classdev_unregister(&pdev->dev, &ild->leds[i].lc);
        if(&ild->leds[i].work)
            cancel_work_sync(&ild->leds[i].work);
    }

    if (ild) {
        if (ild->leds)
            devm_kfree(&pdev->dev, ild->leds);
        devm_kfree(&pdev->dev, ild);
    }
#if LINUX_VERSION_CODE < KERNEL_VERSION(6, 6, 0)
    return 0;
#endif
}

static const struct platform_device_id leds_id_table[] = {
    {"fpga-system-leds", 0},
    {"cpld1-port-leds", 1},
    {"cpld2-port-leds", 2},
    {"sfp-port-leds", 3},
    {  }
};
MODULE_DEVICE_TABLE(platform, leds_id_table);

static struct platform_driver garnet_leds_driver = {
    .driver = {
        .name  = "fpga-system-leds",
        .owner  = THIS_MODULE,
    },
    .probe = garnet_leds_probe,
    .remove = garnet_leds_remove,
    .id_table = leds_id_table,
};

module_platform_driver(garnet_leds_driver);

MODULE_DESCRIPTION("Juniper Networks Garnet System leds driver");
MODULE_AUTHOR("Diwanshu Bansal <diwanshub@juniper.net>");
MODULE_LICENSE("GPL");

