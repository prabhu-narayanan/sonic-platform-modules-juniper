/*
 * Modified hwmon PSU monitoring driver for Juniper QFX5241 platform
 * Supports multiple PSU devices (e.g., at 0x58 and 0x59)
 */

#include <linux/module.h>
#include <linux/jiffies.h>
#include <linux/i2c.h>
#include <linux/hwmon.h>
#include <linux/hwmon-sysfs.h>
#include <linux/err.h>
#include <linux/mutex.h>
#include <linux/sysfs.h>
#include <linux/slab.h>
#include <linux/version.h>

 /* PSU Register definitions */
#define PSU_REG_V_OUT              0x8B    /* READ_VOUT */
#define PSU_REG_V_IN               0x88    /* READ_VIN */
#define PSU_REG_I_OUT              0x8C    /* READ_IOUT */
#define PSU_REG_I_IN               0x89    /* READ_IIN */
#define PSU_REG_P_OUT              0x96    /* READ_POUT */
#define PSU_REG_P_IN               0x97    /* READ_PIN */
#define PSU_REG_VOUT_MODE          0x20    /* VOUT_MODE */
#define PSU_REG_STATUS_WORD        0x79    /* STATUS_WORD */
#define PSU_REG_STATUS_INPUT       0x7C    /* STATUS_INPUT */
#define PSU_REG_STATUS_VOUT        0x7A    /* STATUS_VOUT */
#define PSU_REG_STATUS_IOUT        0x7B    /* STATUS_IOUT */
#define PSU_REG_STATUS_TEMP        0x7D    /* STATUS_TEMPERATURE */
#define PSU_REG_STATUS_FANS        0x81    /* STATUS_FANS_1_2 */
#define PSU_REG_STATUS_OTHER       0x7F    /* STATUS_OTHER */
#define PSU_REG_READ_TEMPERATURE_1 0x8D    /* Ambient Temperature */
#define PSU_REG_MFR_MAX_TEMP_1     0xC0    /* Ambient Temperature Threshold */

static const unsigned short normal_i2c[] = { 0x58, 0x59, I2C_CLIENT_END };

struct psu_data {
    struct device *hwmon_dev;
    struct mutex update_lock;
    char valid;
    unsigned long last_updated;
    u16 v_out, i_out, v_in, i_in;
    u16 p_out, p_in;
    u16 status_word;
    u8 status_input;
    u8 status_vout;
    u8 status_iout;
    u8 status_temperature;
    u8 status_fans;
    u8 status_other;
    s8 vout_mode_exp;  /* LINEAR16 exponent for VOUT */
    u16 temp1_input;   /* Ambient Temperature Value */
    u16 temp1_max;     /* Ambient Temperature Threshold */
};

static ssize_t show_word(struct device *dev, struct device_attribute *da, char *buf);
static struct psu_data *psu_update_device(struct device *dev);

enum psu_sysfs_attributes {
    PSU_V_OUT,
    PSU_I_OUT,
    PSU_V_IN,
    PSU_I_IN,
    PSU_P_IN,
    PSU_P_OUT,
    PSU_STATUS_WORD,
    PSU_STATUS_INPUT,
    PSU_STATUS_VOUT,
    PSU_STATUS_IOUT,
    PSU_STATUS_TEMP,
    PSU_STATUS_FANS,
    PSU_STATUS_OTHER,
    PSU_TEMP1_INPUT,
    PSU_TEMP1_MAX,
};

#define SENSOR_ENTRY(_name, _index) \
    SENSOR_DEVICE_ATTR(_name, S_IRUGO, show_word, NULL, _index)

static SENSOR_ENTRY(output_volt,    PSU_V_OUT);
static SENSOR_ENTRY(output_curr,    PSU_I_OUT);
static SENSOR_ENTRY(input_volt,     PSU_V_IN);
static SENSOR_ENTRY(input_curr,     PSU_I_IN);
static SENSOR_ENTRY(input_power,    PSU_P_IN);
static SENSOR_ENTRY(output_power,   PSU_P_OUT);
static SENSOR_ENTRY(status_word,        PSU_STATUS_WORD);
static SENSOR_ENTRY(status_input,       PSU_STATUS_INPUT);
static SENSOR_ENTRY(status_vout,        PSU_STATUS_VOUT);
static SENSOR_ENTRY(status_iout,        PSU_STATUS_IOUT);
static SENSOR_ENTRY(status_temperature, PSU_STATUS_TEMP);
static SENSOR_ENTRY(status_fans,        PSU_STATUS_FANS);
static SENSOR_ENTRY(status_other,       PSU_STATUS_OTHER);
static SENSOR_ENTRY(temp1_input,        PSU_TEMP1_INPUT);
static SENSOR_ENTRY(temp1_max,          PSU_TEMP1_MAX);

static struct attribute *psu_attributes[] = {
    &sensor_dev_attr_output_volt.dev_attr.attr,
    &sensor_dev_attr_output_curr.dev_attr.attr,
    &sensor_dev_attr_input_volt.dev_attr.attr,
    &sensor_dev_attr_input_curr.dev_attr.attr,
    &sensor_dev_attr_input_power.dev_attr.attr,
    &sensor_dev_attr_output_power.dev_attr.attr,
    &sensor_dev_attr_status_word.dev_attr.attr,
    &sensor_dev_attr_status_input.dev_attr.attr,
    &sensor_dev_attr_status_vout.dev_attr.attr,
    &sensor_dev_attr_status_iout.dev_attr.attr,
    &sensor_dev_attr_status_temperature.dev_attr.attr,
    &sensor_dev_attr_status_fans.dev_attr.attr,
    &sensor_dev_attr_status_other.dev_attr.attr,
    &sensor_dev_attr_temp1_input.dev_attr.attr,
    &sensor_dev_attr_temp1_max.dev_attr.attr,
    NULL
};

static const struct attribute_group jnx_psu_group = {
    .attrs = psu_attributes,
};

/*
 * Decode PMBus LINEAR11 into integer base units, then convert to milli-units.
 * Returned unit depends on register (e.g., V/I/P/T). Caller treats result as
 * millivolts/milliamps/milliwatts/milliC accordingly.
 */
static long pmbus_linear11_milli(u16 value)
{
    s16 exponent, mantissa;
    long result;

    // Extract and sign-extend exponent (bits 15:11)
    exponent = (value >> 11) & 0x1F;
    if (exponent & 0x10)
        exponent |= 0xFFE0;
    // Extract and sign-extend mantissa (bits 10:0)
    mantissa = value & 0x7FF;
    if (mantissa & 0x400)
        mantissa |= 0xF800;

    // Multiply by 1000 *before* shift or divide
    if (exponent < 0)
        result = (long)mantissa * 1000L / (1 << -exponent);
    else
        result = (long)mantissa * 1000L * (1 << exponent);

    return result;
}

/*
 * Decode PMBus LINEAR16 using provided exponent, returning milli-units.
 * Caller treats result as millivolts for VOUT.
 */
static long pmbus_linear16_milli(u16 data, s8 exponent)
{
    s16 mantissa = (s16)data;
    long result;

    // Multiply by 1000 *before* shifting/dividing to preserve precision
    if (exponent < 0)
        result = (long)mantissa * 1000L / (1 << -exponent);
    else
        result = (long)mantissa * 1000L * (1 << exponent);

    return result;
}

/*
 * Helper to format milli-units with 3 decimal places without using floats.
 * Writes into buf and returns number of bytes, similar to sprintf.
 */
static int sprintf_milli(char *buf, long milli)
{
    long abs_milli = milli < 0 ? -milli : milli;
    long integer = abs_milli / 1000L;
    long frac = abs_milli % 1000L;
    if (milli < 0)
        return sprintf(buf, "-%ld.%03ld\n", integer, frac);
    else
        return sprintf(buf, "%ld.%03ld\n", integer, frac);
}

static ssize_t show_word(struct device *dev, struct device_attribute *da, char *buf)
{
    struct sensor_device_attribute *attr = to_sensor_dev_attr(da);
    struct psu_data *data = psu_update_device(dev);

    switch (attr->index) {
    case PSU_V_OUT:
        if (data->v_out == (u16)-1)
            return sprintf(buf, "-1\n");
        return sprintf_milli(buf, pmbus_linear16_milli(data->v_out, data->vout_mode_exp));
    case PSU_V_IN:
        if (data->v_in == (u16)-1)
            return sprintf(buf, "-1\n");
        return sprintf_milli(buf, pmbus_linear11_milli(data->v_in));
    case PSU_I_OUT:
        if (data->i_out == (u16)-1)
            return sprintf(buf, "-1\n");
        return sprintf_milli(buf, pmbus_linear11_milli(data->i_out));
    case PSU_I_IN:
        if (data->i_in == (u16)-1)
            return sprintf(buf, "-1\n");
        return sprintf_milli(buf, pmbus_linear11_milli(data->i_in));
    case PSU_P_OUT:
        if (data->p_out == (u16)-1)
            return sprintf(buf, "-1\n");
        return sprintf_milli(buf, pmbus_linear11_milli(data->p_out));
    case PSU_P_IN:
        if (data->p_in == (u16)-1)
            return sprintf(buf, "-1\n");
        return sprintf_milli(buf, pmbus_linear11_milli(data->p_in));
    case PSU_TEMP1_INPUT:
        if (data->temp1_input == (u16)-1)
            return sprintf(buf, "-1\n");
        return sprintf_milli(buf, pmbus_linear11_milli(data->temp1_input));
    case PSU_TEMP1_MAX:
        if (data->temp1_max == (u16)-1)
            return sprintf(buf, "-1\n");
        return sprintf_milli(buf, pmbus_linear11_milli(data->temp1_max));
    // STATUS REGISTERS: Print as decimal, -1 for error is fine.
    case PSU_STATUS_WORD:
        return sprintf(buf, "%d\n", (int)(s16)data->status_word);
    case PSU_STATUS_INPUT:
        return sprintf(buf, "%d\n", (int)(s8)data->status_input);
    case PSU_STATUS_VOUT:
        return sprintf(buf, "%d\n", (int)(s8)data->status_vout);
    case PSU_STATUS_IOUT:
        return sprintf(buf, "%d\n", (int)(s8)data->status_iout);
    case PSU_STATUS_TEMP:
        return sprintf(buf, "%d\n", (int)(s8)data->status_temperature);
    case PSU_STATUS_FANS:
        return sprintf(buf, "%d\n", (int)(s8)data->status_fans);
    case PSU_STATUS_OTHER:
        return sprintf(buf, "%d\n", (int)(s8)data->status_other);
    }

    /* Unknown attribute */
    return -EINVAL;
}

static int psu_read_word(struct i2c_client *client, u8 reg)
{
    return i2c_smbus_read_word_data(client, reg);
}

static int psu_read_byte(struct i2c_client *client, u8 reg)
{
    return i2c_smbus_read_byte_data(client, reg);
}

struct reg_data_word {
    u8 reg;
    u16 *value;
};

static struct psu_data *psu_update_device(struct device *dev)
{
    struct i2c_client *client = to_i2c_client(dev);
    struct psu_data *data = i2c_get_clientdata(client);

    mutex_lock(&data->update_lock);

    if (time_after(jiffies, data->last_updated + HZ + HZ / 2) || !data->valid) {
        int i, status;
        struct reg_data_word regs[] = {
            {PSU_REG_V_OUT, &data->v_out},
            {PSU_REG_V_IN, &data->v_in},
            {PSU_REG_I_OUT, &data->i_out},
            {PSU_REG_I_IN, &data->i_in},
            {PSU_REG_P_OUT, &data->p_out},
            {PSU_REG_P_IN, &data->p_in},
            {PSU_REG_READ_TEMPERATURE_1, &data->temp1_input}, // Ambient temp
            {PSU_REG_MFR_MAX_TEMP_1, &data->temp1_max},       // Ambient threshold
        };

        for (i = 0; i < ARRAY_SIZE(regs); i++) {
            status = psu_read_word(client, regs[i].reg);
            if (status < 0) {
                *regs[i].value = -1;
            } else {
                *regs[i].value = status;
            }
        }

        /* Read status registers */
        status = psu_read_word(client, PSU_REG_STATUS_WORD);
        data->status_word = (status < 0) ? -1 : (u16)status;
        status = psu_read_byte(client, PSU_REG_STATUS_INPUT);
        data->status_input = (status < 0) ? -1 : (u8)status;
        status = psu_read_byte(client, PSU_REG_STATUS_VOUT);
        data->status_vout = (status < 0) ? -1 : (u8)status;
        status = psu_read_byte(client, PSU_REG_STATUS_IOUT);
        data->status_iout = (status < 0) ? -1 : (u8)status;
        status = psu_read_byte(client, PSU_REG_STATUS_TEMP);
        data->status_temperature = (status < 0) ? -1 : (u8)status;
        status = psu_read_byte(client, PSU_REG_STATUS_FANS);
        data->status_fans = (status < 0) ? -1 : (u8)status;
        status = psu_read_byte(client, PSU_REG_STATUS_OTHER);
        data->status_other = (status < 0) ? -1 : (u8)status;
        data->last_updated = jiffies;
        data->valid = 1;
    }

    mutex_unlock(&data->update_lock);
    return data;
}


static int jnx_psu_probe(struct i2c_client *client
#if LINUX_VERSION_CODE < KERNEL_VERSION(6, 6, 0)
                         , const struct i2c_device_id *id
#endif
)
{
    struct psu_data *data;
    int status;

#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 6, 0)
    const struct i2c_device_id *id = i2c_client_get_device_id(client);
#endif

    if (!i2c_check_functionality(client->adapter, I2C_FUNC_SMBUS_BYTE_DATA |
                        I2C_FUNC_SMBUS_WORD_DATA | I2C_FUNC_SMBUS_I2C_BLOCK))
        return -EIO;

    data = devm_kzalloc(&client->dev, sizeof(struct psu_data), GFP_KERNEL);
    if (!data)
        return -ENOMEM;

    i2c_set_clientdata(client, data);
    mutex_init(&data->update_lock);

    /* Read VOUT_MODE to get LINEAR16 exponent */
    status = i2c_smbus_read_byte_data(client, PSU_REG_VOUT_MODE);
    if (status < 0) {
        dev_warn(&client->dev, 
                 "Failed to read VOUT_MODE (ret=%d), using default exp=-9\n",
                 status);
        data->vout_mode_exp = -9;
    } else {
        /* Extract exponent from bits [4:0], sign-extend if needed */
        data->vout_mode_exp = status & 0x1F;
        if (data->vout_mode_exp & 0x10)
            data->vout_mode_exp -= 32;
        
        dev_info(&client->dev, 
                 "VOUT_MODE=0x%02x, exponent=%d\n",
                 status, data->vout_mode_exp);
    }

    status = sysfs_create_group(&client->dev.kobj, &jnx_psu_group);
    if (status)
        return status;

    data->hwmon_dev = hwmon_device_register(&client->dev);
    if (IS_ERR(data->hwmon_dev)) {
        sysfs_remove_group(&client->dev.kobj, &jnx_psu_group);
        return PTR_ERR(data->hwmon_dev);
    }

    dev_info(&client->dev, "Registered PSU at 0x%02x\n", client->addr);
    return 0;
}

static void jnx_psu_remove(struct i2c_client *client)
{
    struct psu_data *data = i2c_get_clientdata(client);

    hwmon_device_unregister(data->hwmon_dev);
    sysfs_remove_group(&client->dev.kobj, &jnx_psu_group);
}

static const struct i2c_device_id psu_id[] = {
    { "jpsu", 0 },
    { }
};
MODULE_DEVICE_TABLE(i2c, psu_id);

static struct i2c_driver jnx_psu_monitor_driver = {
    .class      = I2C_CLASS_HWMON,
    .driver     = {
        .name   = "garnet-psu-monitor",
    },
    .probe      = jnx_psu_probe,
    .remove     = jnx_psu_remove,
    .id_table   = psu_id,
    .address_list = normal_i2c,
};

module_i2c_driver(jnx_psu_monitor_driver);

MODULE_DESCRIPTION("Juniper Networks Garnet PSU monitoring driver");
MODULE_AUTHOR("Satish Gopalakrishnan <satishg@juniper.net>");
MODULE_LICENSE("GPL");
