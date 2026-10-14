/*
 * Juniper Tmc FPGA register definitions
 *
 * Copyright (C) 2023 Juniper Networks
 * Author: Arun kumar A <arunkumara@juniper.net>
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 as
 * published by the Free Software Foundation.
 */

#ifndef __JNX_GARNET_H__
#define __JNX_GARNET_H__

/*
 * Common definitions
 */
#define OPTIC_CPLDS_MAX                         2

#define GARNET_FPGA_BASE                        0x0000
#define GARNET_CPLD1_BASE                       0x2000
#define GARNET_CPLD1_END                        0x2FFF
#define GARNET_CPLD2_BASE                       0x3000
#define GARNET_CPLD2_END                        0x3FFF

#define ACTN_FPGA_SCRATCH_REG                   (GARNET_FPGA_BASE + 0x004)
#define ACTN_GPIO_FPGA_BEACON_LED_START         (GARNET_FPGA_BASE + 0x086)
#define ACTN_GPIO_FPGA_BEACON_LED_END           (GARNET_FPGA_BASE + 0x088)
#define ACTN_GPIO_FPGA_SYSTEM_LED_START         (GARNET_FPGA_BASE + 0x084)
#define ACTN_GPIO_FPGA_SYSTEM_LED_END           (GARNET_FPGA_BASE + 0x094)

#define ACTN_CPLD1_SCRATCH_REG                  (GARNET_CPLD1_BASE + 0x004)
#define ACTN_GPIO_CPLD1_PRESENCE_START          (GARNET_CPLD1_BASE + 0x088)
#define ACTN_GPIO_CPLD1_PRESENCE_END            (GARNET_CPLD1_BASE + 0x08b)
#define ACTN_GPIO_CPLD1_LPMOD_START             (GARNET_CPLD1_BASE + 0x070)
#define ACTN_GPIO_CPLD1_LPMOD_END               (GARNET_CPLD1_BASE + 0x073)
#define ACTN_GPIO_CPLD1_RESET_START             (GARNET_CPLD1_BASE + 0x078)
#define ACTN_GPIO_CPLD1_RESET_END               (GARNET_CPLD1_BASE + 0x07b)
#define ACTN_GPIO_CPLD1_PWR_GOOD_START          (GARNET_CPLD1_BASE + 0x090)
#define ACTN_GPIO_CPLD1_PWR_GOOD_END            (GARNET_CPLD1_BASE + 0x094)
#define ACTN_GPIO_CPLD1_PORT_LED_START          (GARNET_CPLD1_BASE + 0x0F0)
#define ACTN_GPIO_CPLD1_PORT_LED_END            (GARNET_CPLD1_BASE + 0x0FB)
#define ACTN_GPIO_CPLD1_PORT_LED_DEBUG          (GARNET_CPLD1_BASE + 0x0FC)
#define GARNET_I2C_OCORES_CPLD1_START           (GARNET_CPLD1_BASE + 0x100)
#define GARNET_I2C_OCORES_CPLD1_END             (GARNET_CPLD1_BASE + 0x114)

#define ACTN_CPLD2_SCRATCH_REG                  (GARNET_CPLD2_BASE + 0x004)
#define ACTN_GPIO_CPLD2_PRESENCE_START          (GARNET_CPLD2_BASE + 0x088)
#define ACTN_GPIO_CPLD2_PRESENCE_END            (GARNET_CPLD2_BASE + 0x08b)
#define ACTN_GPIO_CPLD2_LPMOD_START             (GARNET_CPLD2_BASE + 0x070)
#define ACTN_GPIO_CPLD2_LPMOD_END               (GARNET_CPLD2_BASE + 0x073)
#define ACTN_GPIO_CPLD2_RESET_START             (GARNET_CPLD2_BASE + 0x078)
#define ACTN_GPIO_CPLD2_RESET_END               (GARNET_CPLD2_BASE + 0x07b)
#define ACTN_GPIO_CPLD2_SFP28_PRESENCE_START    (GARNET_CPLD2_BASE + 0x009)
#define ACTN_GPIO_CPLD2_SFP28_PRESENCE_END      (GARNET_CPLD2_BASE + 0x009)
#define ACTN_GPIO_CPLD2_SFP28_TX_DIS_START      (GARNET_CPLD2_BASE + 0x007)
#define ACTN_GPIO_CPLD2_SFP28_TX_DIS_END        (GARNET_CPLD2_BASE + 0x007)
#define ACTN_GPIO_CPLD2_SFP28_TX_FAULT_START    (GARNET_CPLD2_BASE + 0x006)
#define ACTN_GPIO_CPLD2_SFP28_TX_FAULT_END      (GARNET_CPLD2_BASE + 0x006)
#define ACTN_GPIO_CPLD2_SFP28_RX_LOS_START      (GARNET_CPLD2_BASE + 0x008)
#define ACTN_GPIO_CPLD2_SFP28_RX_LOS_END        (GARNET_CPLD2_BASE + 0x008)
#define ACTN_GPIO_CPLD2_PWR_GOOD_START          (GARNET_CPLD2_BASE + 0x090)
#define ACTN_GPIO_CPLD2_PWR_GOOD_END            (GARNET_CPLD2_BASE + 0x094)
#define ACTN_GPIO_CPLD2_PORT_LED_START          (GARNET_CPLD2_BASE + 0x0F0)
#define ACTN_GPIO_CPLD2_PORT_LED_END            (GARNET_CPLD2_BASE + 0x0FB)
#define ACTN_GPIO_CPLD2_SFP_PORT_LED_START      (GARNET_CPLD2_BASE + 0x005)
#define ACTN_GPIO_CPLD2_SFP_PORT_LED_END        (GARNET_CPLD2_BASE + 0x005)
#define ACTN_GPIO_CPLD2_PORT_LED_DEBUG          (GARNET_CPLD2_BASE + 0x0FC)
#define GARNET_I2C_OCORES_CPLD2_START           (GARNET_CPLD2_BASE + 0x100)
#define GARNET_I2C_OCORES_CPLD2_END             (GARNET_CPLD2_BASE + 0x114)

#define GARNET_FPGA_MAJOR                       0x0001
#define GARNET_FPGA_MINOR                       0x0002
#define GARNET_OPTIC_CPLD_MAJOR                 0x0000
#define GARNET_OPTIC_CPLD_MINOR                 0x0001

#define GARNET_FPGA_SCRATCH_REG                 (GARNET_FPGA_BASE + 0x004)
#define GARNET_CPLD1_SCRATCH_REG                (GARNET_CPLD1_BASE + 0x004)
#define GARNET_CPLD2_SCRATCH_REG                (GARNET_CPLD2_BASE + 0x004)

#define CHECK_SPI_BUSY(chip, spi_busy_bit)                          \
        while (((ioread32(chip->fpga_membase + 0x30)) >> 24) &  \
                                (1 << spi_busy_bit)) {                  \
                udelay(10);                                     \
    }                                                   \

/*
 * Garnet-64 specific defines
 */
#define GARNET64_GPIO_FPGA_BEACON_LED_START         (GARNET_FPGA_BASE + 0x086)
#define GARNET64_GPIO_FPGA_BEACON_LED_END           (GARNET_FPGA_BASE + 0x088)
#define GARNET64_GPIO_FPGA_SYSTEM_LED_START         (GARNET_FPGA_BASE + 0x084)
#define GARNET64_GPIO_FPGA_SYSTEM_LED_END           (GARNET_FPGA_BASE + 0x094)

#define GARNET64_GPIO_CPLD1_PRESENCE_START          (GARNET_CPLD1_BASE + 0x088)
#define GARNET64_GPIO_CPLD1_PRESENCE_END            (GARNET_CPLD1_BASE + 0x08b)
#define GARNET64_GPIO_CPLD1_LPMOD_START             (GARNET_CPLD1_BASE + 0x070)
#define GARNET64_GPIO_CPLD1_LPMOD_END               (GARNET_CPLD1_BASE + 0x073)
#define GARNET64_GPIO_CPLD1_RESET_START             (GARNET_CPLD1_BASE + 0x078)
#define GARNET64_GPIO_CPLD1_RESET_END               (GARNET_CPLD1_BASE + 0x07b)
#define GARNET64_GPIO_CPLD1_PWR_GOOD_START          (GARNET_CPLD1_BASE + 0x090)
#define GARNET64_GPIO_CPLD1_PWR_GOOD_END            (GARNET_CPLD1_BASE + 0x094)
#define GARNET64_GPIO_CPLD1_PORT_LED_START          (GARNET_CPLD1_BASE + 0x0F0)
#define GARNET64_GPIO_CPLD1_PORT_LED_END            (GARNET_CPLD1_BASE + 0x0FB)
#define GARNET64_GPIO_CPLD1_PORT_LED_DEBUG          (GARNET_CPLD1_BASE + 0x0FC)
#define GARNET64_I2C_OCORES_CPLD1_START             (GARNET_CPLD1_BASE + 0x100)
#define GARNET64_I2C_OCORES_CPLD1_END               (GARNET_CPLD1_BASE + 0x114)

#define GARNET64_GPIO_CPLD2_PRESENCE_START          (GARNET_CPLD2_BASE + 0x088)
#define GARNET64_GPIO_CPLD2_PRESENCE_END            (GARNET_CPLD2_BASE + 0x08b)
#define GARNET64_GPIO_CPLD2_LPMOD_START             (GARNET_CPLD2_BASE + 0x070)
#define GARNET64_GPIO_CPLD2_LPMOD_END               (GARNET_CPLD2_BASE + 0x073)
#define GARNET64_GPIO_CPLD2_RESET_START             (GARNET_CPLD2_BASE + 0x078)
#define GARNET64_GPIO_CPLD2_RESET_END               (GARNET_CPLD2_BASE + 0x07b)
#define GARNET64_GPIO_CPLD2_SFP28_PRESENCE_START    (GARNET_CPLD2_BASE + 0x009)
#define GARNET64_GPIO_CPLD2_SFP28_PRESENCE_END      (GARNET_CPLD2_BASE + 0x009)
#define GARNET64_GPIO_CPLD2_SFP28_TX_DIS_START      (GARNET_CPLD2_BASE + 0x007)
#define GARNET64_GPIO_CPLD2_SFP28_TX_DIS_END        (GARNET_CPLD2_BASE + 0x007)
#define GARNET64_GPIO_CPLD2_SFP28_TX_FAULT_START    (GARNET_CPLD2_BASE + 0x006)
#define GARNET64_GPIO_CPLD2_SFP28_TX_FAULT_END      (GARNET_CPLD2_BASE + 0x006)
#define GARNET64_GPIO_CPLD2_SFP28_RX_LOS_START      (GARNET_CPLD2_BASE + 0x008)
#define GARNET64_GPIO_CPLD2_SFP28_RX_LOS_END        (GARNET_CPLD2_BASE + 0x008)
#define GARNET64_GPIO_CPLD2_PWR_GOOD_START          (GARNET_CPLD2_BASE + 0x090)
#define GARNET64_GPIO_CPLD2_PWR_GOOD_END            (GARNET_CPLD2_BASE + 0x093)
#define GARNET64_GPIO_CPLD2_PORT_LED_START          (GARNET_CPLD2_BASE + 0x0F0)
#define GARNET64_GPIO_CPLD2_PORT_LED_END            (GARNET_CPLD2_BASE + 0x0FB)
#define GARNET64_GPIO_CPLD2_SFP_PORT_LED_START      (GARNET_CPLD2_BASE + 0x005)
#define GARNET64_GPIO_CPLD2_SFP_PORT_LED_END        (GARNET_CPLD2_BASE + 0x005)
#define GARNET64_GPIO_CPLD2_PORT_LED_DEBUG          (GARNET_CPLD2_BASE + 0x0FC)
#define GARNET64_I2C_OCORES_CPLD2_START             (GARNET_CPLD2_BASE + 0x100)
#define GARNET64_I2C_OCORES_CPLD2_END               (GARNET_CPLD2_BASE + 0x114)

#define GARNET64_PSU_START                          (0x4)
#define GARNET64_PSU_END                            (0x7)

/*
 * Garnet-32 specific defines
 */
#define GARNET32_NUM_PORTS_CPLD1                    (16)
#define GARNET32_NUM_PORTS_CPLD2                    (18)
#define GARNET32_GPIO_FPGA_BEACON_LED_START         (GARNET_FPGA_BASE + 0x086)
#define GARNET32_GPIO_FPGA_BEACON_LED_END           (GARNET_FPGA_BASE + 0x088)
#define GARNET32_GPIO_FPGA_SYSTEM_LED_START         (GARNET_FPGA_BASE + 0x084)
#define GARNET32_GPIO_FPGA_SYSTEM_LED_END           (GARNET_FPGA_BASE + 0x094)

#define GARNET32_CPLD_OCORES_OFFSET                 (0x20)
#define GARNET32_CPLD_OCORES_INBAND_OFFSET          (0x400)
#define GARNET32_GPIO_CPLD1_PRESENCE_START          (GARNET_CPLD1_BASE + 0x088)
#define GARNET32_GPIO_CPLD1_PRESENCE_END            (GARNET_CPLD1_BASE + 0x089)
#define GARNET32_GPIO_CPLD1_LPMOD_START             (GARNET_CPLD1_BASE + 0x070)
#define GARNET32_GPIO_CPLD1_LPMOD_END               (GARNET_CPLD1_BASE + 0x071)
#define GARNET32_GPIO_CPLD1_RESET_START             (GARNET_CPLD1_BASE + 0x078)
#define GARNET32_GPIO_CPLD1_RESET_END               (GARNET_CPLD1_BASE + 0x079)
#define GARNET32_GPIO_CPLD1_PWR_GOOD_START          (GARNET_CPLD1_BASE + 0x005)
#define GARNET32_GPIO_CPLD1_PWR_GOOD_END            (GARNET_CPLD1_BASE + 0x00B)
#define GARNET32_GPIO_CPLD1_PORT_LED_START          (GARNET_CPLD1_BASE + 0x0F0)
#define GARNET32_GPIO_CPLD1_PORT_LED_END            (GARNET_CPLD1_BASE + 0x0F5)
#define GARNET32_GPIO_CPLD1_PORT_LED_DEBUG          (GARNET_CPLD1_BASE + 0x0F6)
#define GARNET32_I2C_OCORES_CPLD1_START             (GARNET_CPLD1_BASE + 0x100)
#define GARNET32_I2C_OCORES_CPLD1_END               (GARNET_CPLD1_BASE + 0x114)

#define GARNET32_GPIO_CPLD2_PRESENCE_START          (GARNET_CPLD2_BASE + 0x088)
#define GARNET32_GPIO_CPLD2_PRESENCE_END            (GARNET_CPLD2_BASE + 0x089)
#define GARNET32_GPIO_CPLD2_LPMOD_START             (GARNET_CPLD2_BASE + 0x070)
#define GARNET32_GPIO_CPLD2_LPMOD_END               (GARNET_CPLD2_BASE + 0x071)
#define GARNET32_GPIO_CPLD2_RESET_START             (GARNET_CPLD2_BASE + 0x078)
#define GARNET32_GPIO_CPLD2_RESET_END               (GARNET_CPLD2_BASE + 0x079)
#define GARNET32_GPIO_CPLD2_SFP28_PRESENCE_START    (GARNET_CPLD2_BASE + 0x009)
#define GARNET32_GPIO_CPLD2_SFP28_PRESENCE_END      (GARNET_CPLD2_BASE + 0x009)
#define GARNET32_GPIO_CPLD2_SFP28_TX_DIS_START      (GARNET_CPLD2_BASE + 0x007)
#define GARNET32_GPIO_CPLD2_SFP28_TX_DIS_END        (GARNET_CPLD2_BASE + 0x007)
#define GARNET32_GPIO_CPLD2_SFP28_TX_FAULT_START    (GARNET_CPLD2_BASE + 0x006)
#define GARNET32_GPIO_CPLD2_SFP28_TX_FAULT_END      (GARNET_CPLD2_BASE + 0x006)
#define GARNET32_GPIO_CPLD2_SFP28_RX_LOS_START      (GARNET_CPLD2_BASE + 0x008)
#define GARNET32_GPIO_CPLD2_SFP28_RX_LOS_END        (GARNET_CPLD2_BASE + 0x008)
#define GARNET32_GPIO_CPLD2_PWR_GOOD_START          (GARNET_CPLD2_BASE + 0x090)
#define GARNET32_GPIO_CPLD2_PWR_GOOD_END            (GARNET_CPLD2_BASE + 0x091)
#define GARNET32_GPIO_CPLD2_PORT_LED_START          (GARNET_CPLD2_BASE + 0x0F0)
#define GARNET32_GPIO_CPLD2_PORT_LED_END            (GARNET_CPLD2_BASE + 0x0F5)
#define GARNET32_GPIO_CPLD2_PORT_LED_DEBUG          (GARNET_CPLD2_BASE + 0x0F9)
#define GARNET32_GPIO_CPLD2_SFP_PORT_LED_START      (GARNET_CPLD2_BASE + 0x005)
#define GARNET32_GPIO_CPLD2_SFP_PORT_LED_END        (GARNET_CPLD2_BASE + 0x005)
#define GARNET32_I2C_OCORES_CPLD2_START             (GARNET_CPLD2_BASE + 0x100)
#define GARNET32_I2C_OCORES_CPLD2_END               (GARNET_CPLD2_BASE + 0x114)

#define GARNET32_PSU_START                          (0x4)
#define GARNET32_PSU_END                            (0x7)

/*
 * Structure definitions
 */
struct garnet_optic_cpld_version {
        u32 optic_cpld_major; /* optic cpld major version */
        u32 optic_cpld_minor; /* optic cpld minor version */
        u32 optic_cpld_devid; /* optic cpld device id */
};

struct garnet_fpga_data {
        void __iomem *fpga_membase;
        void __iomem *cpld1_membase;
        void __iomem *cpld2_membase;
        struct pci_dev *pdev;

        u32 major;   /* Device id & Major version*/
        u32 minor;      /* Minor version */

        struct garnet_optic_cpld_version ocpld[OPTIC_CPLDS_MAX];
        struct mutex lock[OPTIC_CPLDS_MAX];
        int spi_busy_bit;
        bool no_lock;
};

typedef struct _garnet_i2c_pdata {
        u32 reg_shift; /* register offset shift value */
        u32 reg_io_width; /* register io read/write width */
        u32 clock_khz; /* input clock in kHz */
        u32 bus_khz; /* bus clock in kHz */
        bool big_endian; /* registers are big endian */
        u8 num_devices; /* number of devices in the devices list */
        int i2c_bus_num; /* desired static i2c bus number; -1 = dynamic */
} garnet_i2c_pdata_t;

#endif /* __JNX_GARNET_H__ */
