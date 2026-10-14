/*
 *  Altera Fan CPLD (jnx-s32afc-core) registers
 *
 * Copyright (C) 2018 Juniper Networks
 * Author: Diwas Kumar <diwask@juniper.net>
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 as
 * published by the Free Software Foundation.
 */

#ifndef __JNX_S32AFC_CORE_H__
#define __JNX_S32AFC_CORE_H__


/* Board Info Register */
#define ALTERA_BOARD_INFO_REG                   0x00
#define ALTERA_CPLD_VERSION_REG                 0x01
#define ALTERA_FAN_CPLD_RESET_REG               0x04
#define ALTERA_INTERRUPT_STATUS_REG             0x05
#define ALTERA_INTERRUPT_MASK_REG               0x06

/* Present detection register */
#define ALTERA_FAN_MODULE_PRESENT_REG           0x0F

/* Fan module Direction register */
#define ALTERA_FAN_MODULE_DIR_REG               0x10

/* Register to control Fan PWM value */
#define ALTERA_FAN_MODULE_PWM_REG               0x11

/* Front Fan module speed */

/* Fan 11 */
#define ALTERA_F_FAN_5_SPEED_REG                0x12
/* Fan 9 */
#define ALTERA_F_FAN_4_SPEED_REG                0x13
/* Fan 7 */
#define ALTERA_F_FAN_3_SPEED_REG                0x14
/* Fan 5 */
#define ALTERA_F_FAN_2_SPEED_REG                0x15
/* Fan 3 */
#define ALTERA_F_FAN_1_SPEED_REG                0x16
/* Fan 1 */
#define ALTERA_F_FAN_0_SPEED_REG                0x17

/* Rear Fan module speed */
/* Fan 12*/
#define ALTERA_R_FAN_5_SPEED_REG                0x22
/* Fan 10 */
#define ALTERA_R_FAN_4_SPEED_REG                0x23
/* Fan 8 */
#define ALTERA_R_FAN_3_SPEED_REG                0x24
/* Fan 6 */
#define ALTERA_R_FAN_2_SPEED_REG                0x25
/* Fan 4 */
#define ALTERA_R_FAN_1_SPEED_REG                0x26
/* Fan 2 */
#define ALTERA_R_FAN_0_SPEED_REG                0x27

/* LED control regs on Fan module */
#define ALTERA_FAN_LED_DISPLAY_1_REG            0x1C
#define ALTERA_FAN_LED_DISPLAY_2_REG            0x1D

#define ALTERA_FAN_MODULE_POWER_ENABLE_REG      0x30
#define ALTERA_FAN_WD_TIMER_REG                 0x31
#define ALTERA_FAN_WD_MAX_PWM_REG               0x32
#define ALTERA_FAN_WD_DISABLE_REG               0x33
#define ALTERA_FAN_LED_DEBUG_MODE_REG           0x42

#define MAX_REGMAP_REG  ALTERA_FAN_LED_DEBUG_MODE_REG


/* Datasheet says to multiply the tach register value with the Tach factor
 * to get the RPM
 */
#define ALTERA_FAN_TACH_FACTOR                  100
#define ALTERA_FAN_MAX_NUM                      12

/*
 * Bit[3:0] is valid. Bit[7:4] is reserved. So always mask the PWM read/write
 * with the value 2^4-1 = 0x0F.
 */
#define ALTERA_FAN_MODULE_PWM_MASK              0x0F

/* PWM calculation:
 * PWM register represents dutycycle from 0% to 100%.
 * With 4 bit[3:0] resolution, 0-100 is stepped at 100/(2^4) = 6.75%
 */

/* Default the PWM range to be from 0-255. */
#define ALTERA_FAN_MODULE_PWM_MAX                       0xFF /* 255 decimal */
#define ALTERA_FAN_MODULE_DUTY_CYCLE_MAX                0x64 /* 100 decimal*/
/* When all bits of PWM reg is 0 */
#define ALTERA_FAN_MODULE_PWM_MIN                       0x0F /* 15 decimal */
#define ALTERA_FAN_MODULE_DUTY_CYCLE_MIN                0x06

#endif /*__JNX_S32AFC_CORE_H__*/
