/*
 * Juniper XRE FPGA (over LPC) register definitions
 *
 * Copyright (C) 2020 Juniper Networks
 * Author: Vaibhav Agarwal <avaibhav@juniper.net>
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 as
 * published by the Free Software Foundation.
 */

#ifndef __JNX_XREFPGA_LPCM_H__
#define __JNX_XREFPGA_LPCM_H__

#include <linux/bitops.h>

#define JNX_XREFPGA_LPCM_VERSION_MAJOR                  0x000
#define JNX_XREFPGA_LPCM_VERSION_MINOR                  0x001
#define JNX_XREFPGA_LPCM_SCRATCH                        0x002
#define JNX_XREFPGA_LPCM_RST_CTL                        0x003
#define JNX_XREFPGA_LPCM_SYS_LED                        0x005
#define JNX_XREFPGA_LPCM_PSU_CTL                        0x010
#define JNX_XREFPGA_LPCM_I2C_CTL                        0x011
#define JNX_XREFPGA_LPCM_PWR_CTL                        0x012
#define JNX_XREFPGA_LPCM_PSU_STS                        0x015
#define JNX_XREFPGA_LPCM_PWR_STS                        0x016
#define JNX_XREFPGA_LPCM_IRQ_STS                        0x019
#define JNX_XREFPGA_LPCM_IRQ_ENABLE                     0x01A
#define JNX_XREFPGA_LPCM_BRD_STS                        0x020
#define JNX_XREFPGA_LPCM_BD_UPDATE                      0x021
#define JNX_XREFPGA_LPCM_PWR_DIS_CAUSE                  0x023
#define JNX_XREFPGA_LPCM_PWR_VFAIL_CAUSE_A              0x024
#define JNX_XREFPGA_LPCM_PWR_VFAIL_CAUSE_B              0x025
#define JNX_XREFPGA_LPCM_FCFG_ENB                       0x07A
#define JNX_XREFPGA_LPCM_FCFG_WB_CTL                    0x07D
#define JNX_XREFPGA_LPCM_FCFG_WB_DATA                   0x07E
#define JNX_XREFPGA_LPCM_UPDATE_ENABLED                 0x0FC
#define JNX_XREFPGA_LPCM_IDPROM                         0x100
#define JNX_XREFPGA_LPCM_CBIOS_BASE                     0x200

#define JNX_XREFPGA_LPCM_IRQ_NR                         8
#define JNX_XREFPGA_LPCM_IRQ_MASK       (BIT(JNX_XREFPGA_LPCM_IRQ_NR) - 1)

#define JNX_XREFPGA_LPCM_REG_ADDR(_lpc, _reg) \
                        (((_lpc)->base) + (_reg))

#define JNX_XREFPGA_LPCM_CPU_UPDATE_WP  BIT(2)
#define JNX_XREFPGA_LPCM_MB_NONJTAC_UPDATE_WP   BIT(5)

#define JNX_XREFPGA_LPCM_FCFG_RSTE      BIT(6)
#define JNX_XREFPGA_LPCM_FCFG_WBCE      BIT(7)
#define JNX_XREFPGA_LPCM_FCFG_DATA0     0x79
#define JNX_XREFPGA_LPCM_FCFG_DATA1     0x00
#define JNX_XREFPGA_LPCM_FCFG_DATA2     0x00

#define JNX_XREFPGA_LPCM_IRQ_DCDCHG     BIT(6)
#define JNX_XREFPGA_LPCM_UART_DCD       BIT(1)
#endif /* __JNX_XREFPGA_LPCM_H__ */
