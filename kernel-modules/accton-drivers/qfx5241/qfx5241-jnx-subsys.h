/*
 * Juniper Generic APIs for providing chassis and card information
 *
 * Copyright (C) 2012, 2013, 2014 Juniper Networks. All rights reserved.
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 */

#ifndef _JNX_SUBSYS_H
#define _JNX_SUBSYS_H

#include <linux/nvmem-consumer.h>

/*
 * Juniper Product Number Definitions
 */
#define JNX_PRODUCT_HERCULES    7
#define JNX_PRODUCT_SANGRIA     85
#define JNX_PRODUCT_TINY        134
#define JNX_PRODUCT_HENDRICKS   156
#define JNX_PRODUCT_POLARIS     171
#define JNX_PRODUCT_OMEGA       199
#define JNX_PRODUCT_PTX5K_MTRCB JNX_PRODUCT_SANGRIA     /* product ID is same */
#define JNX_PRODUCT_DCF_PINNACLE        202
#define JNX_PRODUCT_BRACKLA_16T 220
#define JNX_PRODUCT_BRACKLA_8T  233
#define JNX_PRODUCT_VALE_16_PTX 236
#define JNX_PRODUCT_ATTELLA     238
#define JNX_PRODUCT_SAPPHIRE_32CD       242
#define JNX_PRODUCT_SAPPHIRE_128C       243
#define JNX_PRODUCT_ARDBEG_MAINBOARD    239
#define JNX_PRODUCT_ARDBEG_36MR         251
#define JNX_PRODUCT_SPECTROLITE_32CD    253
#define JNX_PRODUCT_ACX753              252
#define JNX_PRODUCT_XMEN_48L_QFX        256
#define JNX_PRODUCT_XMEN_32C            257
#define JNX_PRODUCT_XMEN_48L_ACX        258
#define JNX_PRODUCT_QFX5700             260
#define JNX_PRODUCT_ACX753_RP2400       261
#define JNX_PRODUCT_ACX7908             270
#define JNX_PRODUCT_ACX724              271
#define JNX_PRODUCT_TOMATIN             276
#define JNX_PRODUCT_GARNET_OSFP_64OD    284
#define JNX_PRODUCT_GARNET_QSFPDD_64CD  285

#define JNX_BRD_I2C_NAME_LEN    24

struct jnx_card_info {
        u16 assembly_id;
        int slot;
        u32 type;
        void *data;
        struct i2c_adapter *adap;
};

struct jnx_chassis_info {
        u32 platform;
        u32 chassis_no;
        u32 multichassis;
        bool rel_mastership_on_oops;
        void *master_data;
        int (*get_master)(void *data);
        bool (*mastership_get)(void *data);
        void (*mastership_set)(void *data, bool mastership);
        void (*mastership_ping)(void *data);
        int (*mastership_count_get)(void *data);
        int (*mastership_count_set)(void *data, int val);
};

/* mastership related */
int register_mastership_notifier(struct notifier_block *nb);
int unregister_mastership_notifier(struct notifier_block *nb);
bool jnx_is_master(void);

int jnx_register_board(struct device *edev, struct device *ideeprom,
                       struct jnx_card_info *cinfo, int id);
int jnx_unregister_board(struct device *edev);
int jnx_sysfs_create_link(struct device *dev, const char *link);
void jnx_sysfs_delete_link(struct device *dev, const char *link);
int jnx_sysfs_create_local_dev_link(struct device *dev, const char *link);
void jnx_sysfs_delete_local_dev_link(struct device *dev, const char *link);
int jnx_local_card_exists(void);
void jnx_set_platform(int val);
int jnx_register_local_card(struct jnx_card_info *cinfo);
void jnx_unregister_local_card(void);
int jnx_register_chassis(struct jnx_chassis_info *chinfo);
void jnx_unregister_chassis(void);
int     jnx_mastership_updated(void);

/*      API testing warmboot: != 0: warmboot, == 0: coldboot */
bool    jnx_warmboot(void);

#define JNX_PLATFORM_UEVENT_OBJ_LEN             32
#define JNX_PLATFORM_UEVENT_SUB_LEN             32

typedef int (*jnx_get_assembly_id_callback)(struct nvmem_device *nvmem,
                                            void *buf);
void jnx_register_eeprom_read_callback(jnx_get_assembly_id_callback ptr_func);
int jnx_platform_assembly_id_read(struct nvmem_device *nvmem, void *buf);

#endif /* _JNX_SUBSYS_H */
