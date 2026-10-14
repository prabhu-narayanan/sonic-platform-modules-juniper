/*
 * Garnet Fan CPLD (jnx-garnet-fancpld) register definitions
 *
 * Copyright (C) 2023 Juniper Networks
 * Author: Rahul Mishra <mishrar@juniper.net>
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 as
 * published by the Free Software Foundation.
 */


#ifndef __JNX_GARNET_FANCPLD_H__
#define __JNX_GARNET_FANCPLD_H__

/* Board Info Register */
#define GARNET_BOARD_INFO_REG                   0x00
#define GARNET_BOARD_ID_MASK                    0x03
#define GARNET_BOARD_VERSION_ID_MASK            0x70
#define GARNET_CPLD_MAJOR_VER_REG               0x01
#define GARNET_CPLD_MINOR_VER_REG               0x02
#define GARNET_SCRATCH_PAD_REG                  0x04


/* Fan power enable/disable and protect/unprotect EEPROM
 * [B7]: Fan 1 write protect EEPROM
 * [B6]: Fan 2 write protect EEPROM
 * [B5]: Fan 3 write protect EEPROM
 * [B4]: Fan 4 write protect EEPROM
 * [B3]: Fan 1 enable power
 * [B2]: Fan 2 enable power
 * [B1]: Fan 3 enable power
 * [B0]: Fan 4 enable power
 */
#define GARNET_FAN_PWR_EN_EEPROM_WP             0x05


/* LED control reg
 * [B7]: Fan 4 Green
 * [B6]: Fan 4 Red
 * [B5]: Fan 3 Green 
 * [B4]: Fan 3 Red
 * [B3]: Fan 2 Green
 * [B2]: Fan 2 Red
 * [B1]: Fan 1 Green
 * [B0]: Fan 1 Red
 */
#define GARNET_FAN_LED                          0x06


/* Fan Present Reg and fine tune enable reg
 * [B7]: Fan 1 Present
 * [B6]: Fan 2 Present
 * [B5]: Fan 3 Present
 * [B4]: Fan 4 Present
 * [B3-B1]: Reserved 
 * [B0]: Fan Tach fine tune enable
 */
#define GARNET_FAN_PRESENT_FINE_TUNE_EN         0x07


/* Misc Reg of Fan CPLD
 * [B7]: Card presnt
 * [B6]: CPLD UPD Disable
 * [B5]: Temp sensor alert2 
 * [B4]: Temp sensor alert1
 * [B3]: Power good Fan 4
 * [B2]: Power good Fan 3
 * [B1]: Power good Fan 2
 * [B0]: Power good Fan 1
 */
#define GARNET_MISC_REG                         0x08
#define GARNET_I2C_RELAY_FAIL_CHANNEL           0x09


/* Front Fan PWM reg 
 * [B7-B4]: Reserved
 * [B3-B0]: PWM control
 */
/* Fan 1 PWM */
#define GARNET_FAN_4_PWM_F                      0x10
/* Fan 3 PWM */
#define GARNET_FAN_3_PWM_F                      0x12
/* Fan 5 PWM */
#define GARNET_FAN_2_PWM_F                      0x14
/* Fan 7 PWM */
#define GARNET_FAN_1_PWM_F                      0x16


/* Rear Fan PWM reg
 * [B7-B4]: Reserved
 * [B3-B0]: PWM control
 */
/* Fan 2 PWM */
#define GARNET_FAN_4_PWM_B                      0x11
/* Fan 4 PWM */
#define GARNET_FAN_3_PWM_B                      0x13
/* Fan 6 PWM */
#define GARNET_FAN_2_PWM_B                      0x15
/* Fan 8 PWM */
#define GARNET_FAN_1_PWM_B                      0x17


/* Front Fan module speed */
/* Fan 1 */
#define GARNET_FAN_4_TACH_F                     0x20
/* Fan 3 */
#define GARNET_FAN_3_TACH_F                     0x22
/* Fan 5 */
#define GARNET_FAN_2_TACH_F                     0x24
/* Fan 7 */
#define GARNET_FAN_1_TACH_F                     0x26


/* Rear Fan module speed */
/* Fan 2 */
#define GARNET_FAN_4_TACH_B                     0x21
/* Fan 4 */
#define GARNET_FAN_3_TACH_B                     0x23
/* Fan 6 */
#define GARNET_FAN_2_TACH_B                     0x25
/* Fan 8 */
#define GARNET_FAN_1_TACH_B                     0x27


/* Finetune target tach Front Fan */
#define GARNET_FAN_4_TARGET_TACH_F              0x30
#define GARNET_FAN_3_TARGET_TACH_F              0x32
#define GARNET_FAN_2_TARGET_TACH_F              0x34
#define GARNET_FAN_1_TARGET_TACH_F              0x36


/* Finetune target tach Rear Fan */
#define GARNET_FAN_4_TARGET_TACH_B              0x31
#define GARNET_FAN_3_TARGET_TACH_B              0x33
#define GARNET_FAN_2_TARGET_TACH_B              0x35
#define GARNET_FAN_1_TARGET_TACH_B              0x37


/* Finetuned Tach-results check with Real Tach for Front Fan */
#define GARNET_FAN_4_FINETUNE_TACH_F            0x40
#define GARNET_FAN_3_FINETUNE_TACH_F            0x42
#define GARNET_FAN_2_FINETUNE_TACH_F            0x44
#define GARNET_FAN_1_FINETUNE_TACH_F            0x46


/* Finetuned Tach-results check with Real Tach for Rear Fan */
#define GARNET_FAN_4_FINETUNE_TACH_B            0x41
#define GARNET_FAN_3_FINETUNE_TACH_B            0x43
#define GARNET_FAN_2_FINETUNE_TACH_B            0x45
#define GARNET_FAN_1_FINETUNE_TACH_B            0x47

#define MAX_REGMAP_REG  GARNET_FAN_1_FINETUNE_TACH_B

/* As per the datasheet, multiply the tach register value with the Tach factor
 * to get the RPM
 */
#define GARNET_FAN_TACH_FACTOR                  150
#define GARNET_FAN_MAX_NUM                      8


/* As per the datasheet, Bit[7:4] is reserved and Bit[3:0] is valid.
 * So always mask the PWM read/write with the value 2^4-1 = 0x0F.
 */
#define GARNET_FAN_MODULE_PWM_MASK              0x0F


/* PWM calculation:
 * PWM register represents dutycycle from 0% to 100%.
 * With 4 bit[3:0] resolution, 0-100 is stepped at 100/(2^4) = 6.75%
 */
#define GARNET_FAN_MODULE_PWM_MAX               0xFF /* 255 decimal */
#define GARNET_FAN_MODULE_DUTY_CYCLE_MAX        0x64 /* 100 decimal*/

/* When all bits of PWM reg is 0 */
#define GARNET_FAN_MODULE_PWM_MIN               0x00 /* 15 decimal */
#define GARNET_FAN_MODULE_DUTY_CYCLE_MIN        0x00

#endif /* __JNX_GARNET_FANCPLD_H__ */
