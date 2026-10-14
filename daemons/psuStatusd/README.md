# psuStatusd - PSU Extended Fault Monitoring Daemon

## Overview

Host-based systemd daemon that provides comprehensive PSU fault monitoring for Juniper QFX5241 platforms. Monitors PMBus status registers and publishes detailed fault information to STATE_DB, enabling proactive detection of PSU issues beyond basic presence/power-good checks provided by the standard SONiC `psud` daemon.

**Key Differentiator**: While `psud` monitors basic PSU health (presence, power good, voltage/current readings), `psuStatusd` adds **granular fault diagnostics** by reading platform-specific PMBus status registers and detecting the **specific type** of each fault (e.g., "Fan 1 Fault" vs just "fan problem").

---

## Architecture

### System Components

```
Hardware Layer:
    PSU Hardware (0x58, 0x59 on I2C bus)
           ↓
    I2C/PMBus Protocol
           ↓
Kernel Layer:
    qfx5241-jnx-garnet-psu-monitor.ko (kernel driver)
           ↓
    hwmon sysfs (/sys/class/hwmon/hwmon*/device/status_*)
           ↓
Platform API Layer:
    psu.py (/usr/lib/python3/dist-packages/sonic_platform/psu.py)
           ↓
Daemon Layer:
    psuStatusd (host systemd service, polls every 3 seconds)
           ↓
Database Layer:
    STATE_DB (Redis database 6)
```

### Deployment

- **Location**: Host OS (not inside pmon container), managed by systemd
- **Platform API**: `psu.py` exists in two locations:
  - Host: `/usr/lib/python3/dist-packages/sonic_platform/psu.py` (used by psuStatusd)
  - Container: `/usr/local/lib/python3.11/dist-packages/sonic_platform/psu.py` (used by psud)
  - In production, these are the same file via symlink/mount
- **Polling**: Every 3 seconds (synchronized with psud)

---

## Monitored PMBus Registers

| Register | Address | Method | Fault Types |
|----------|---------|--------|-------------|
| STATUS_INPUT | 0x7C | `get_input_voltage_status()` | Input under/over voltage, unit off |
| STATUS_VOUT | 0x7A | `get_output_voltage_status()` | Output under/over voltage |
| STATUS_IOUT | 0x7B | `get_output_current_status()` | Output over current/power |
| STATUS_TEMPERATURE | 0x7D | `get_temperature_status()` | Over temperature |
| STATUS_FANS | 0x81 | `get_fan_status()` | Fan 1/2 faults and warnings |
| STATUS_OTHER | 0x7F | `get_input_feed_status()` | Input feed failure (one-time) |
| STATUS_WORD | 0x79 | `get_status()` | Composite health check |

---

## State DB Schema

### Fields Added by psuStatusd

Adds **14 fields** per PSU to `PSU_INFO|PSU{1|2}`:

```
# One-time input feed check (at daemon startup)
input_feed_status: "OK" | "Fault"
input_feed_fault: "N/A" | "Feed Failure"
input_feed_checked: "true"

# Continuous monitoring (every 3 seconds)
input_voltage_status: "OK" | "Fault"
input_voltage_fault: "N/A" | "Under Voltage" | "Over Voltage" | "Unit Off"

output_voltage_status: "OK" | "Fault"
output_voltage_fault: "N/A" | "Under Voltage" | "Over Voltage"

output_current_status: "OK" | "Fault"
output_current_fault: "N/A" | "Over Current" | "Over Current Warning"

temp_fault_status: "OK" | "Fault"
temp_fault_fault: "N/A" | "Over Temperature" | "Over Temperature Warning"

fan_status: "OK" | "Fault"
fan_fault: "N/A" | "Fan 1 Fault" | "Fan 2 Fault" | "Fan 1 Warning" | "Fan 2 Warning"

fault_monitoring_updated: "2025-10-30 21:07:30"
```

### Relationship with psud

Both daemons write to the same `PSU_INFO` table but manage **different fields**:
- **psud**: `presence`, `status`, `voltage`, `current`, `power`, `model`, `serial`, etc.
- **psuStatusd**: Detailed fault status fields (listed above)

---

## Logging

### Behavior

**Change-detection logging** - logs only when fault status changes:

```python
# Fault detected
self.log_warning("PSU1 fan fault: Fan 1 Fault")

# Fault cleared
self.log_notice("PSU1 fan fault cleared")
```

**No faults = no logs** (this is normal and expected!)

### Log Levels

- **INFO**: Daemon startup, State DB connection
- **NOTICE**: Fault cleared
- **WARNING**: Fault detected
- **ERROR**: Critical failures (input feed)

### Viewing Logs

```bash
# Real-time
sudo journalctl -u psuStatusd -f

# Recent warnings/errors
sudo journalctl -u psuStatusd -p warning -n 50

# Syslog
sudo grep psuStatusd /var/log/syslog | tail -50
```

### Example Output

```
Oct 30 21:06:45 sonic WARNING psuStatusd[2039046]: PSU1 fan fault: Fan 1 Fault
Oct 30 21:06:45 sonic WARNING psuStatusd[2039046]: PSU2 fan fault: Fan 1 Fault
Oct 30 21:07:12 sonic NOTICE psuStatusd[2039046]: PSU1 fan fault cleared
```

---

## Testing

### Test Script Architecture

Fault injection scripts simulate hardware failures by temporarily modifying `psu.py`:

```bash
# Workflow
1. Backup psu.py (both host and container)
2. Inject fault (modify get_*_status() to return fault)
3. Restart both daemons
4. Monitor logs for 30 seconds
5. Check STATE_DB
6. Restore original psu.py
7. Restart daemons
```

### Why Modify Both Locations?

During development, host and container have separate `psu.py` files. Test scripts must update both so `psuStatusd` (host) and `psud` (container) both see the injected fault. In production, these are the same file.

### Example Tests

```bash
/tmp/test_fan_fault.sh              # Fan failure
/tmp/test_temp_fault.sh             # Over temperature
/tmp/test_input_voltage_fault.sh    # Input voltage
/tmp/test_output_voltage_fault.sh   # Output voltage
/tmp/test_output_current_fault.sh   # Output current
```

### Running a Test

```bash
sudo /tmp/test_fan_fault.sh

# Expected:
# - Logs: "PSU1 fan fault: Fan 1 Fault"
# - STATE_DB: fan_status: "Fault"
# - Auto-restore original code
```

---

## Installation

### Automatic (Image Build)

Integrated via `sonic_debian_extension.j2`:

```bash
/usr/local/bin/psuStatusd          # Daemon binary
/lib/systemd/system/psuStatusd.service  # Systemd unit
```

### Manual (Development)

```bash
sudo cp psuStatusd /usr/local/bin/
sudo chmod +x /usr/local/bin/psuStatusd
sudo cp psuStatusd.service /lib/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable psuStatusd
sudo systemctl start psuStatusd
```

---

## Management

```bash
# Status
sudo systemctl status psuStatusd

# Control
sudo systemctl start|stop|restart psuStatusd

# Logs
sudo journalctl -u psuStatusd -f

# STATE_DB
redis-cli -n 6 HGETALL "PSU_INFO|PSU1"
redis-cli -n 6 HGETALL "PSU_INFO|PSU2"

# Check fault fields
redis-cli -n 6 HGETALL "PSU_INFO|PSU1" | grep -E "(status|fault)"
```

---

## Dependencies

- **psu.py**: Platform API at `/usr/lib/python3/dist-packages/sonic_platform/psu.py`
- **Kernel driver**: `qfx5241-jnx-garnet-psu-monitor.ko` exposing PMBus via hwmon
- **database.service**: Redis STATE_DB
- **Python packages**: `sonic_platform`, `sonic_py_common`, `swsscommon`
- **Hardware**: QFX5241 PSUs at I2C 0x58, 0x59

---

## Known Limitations

- **Input feed**: One-time check at startup (not continuous)
- **Multi-PSU faults**: No automatic correlation (check logs manually)
- **MCU access**: I2C errors not explicitly tracked
- **Polling interval**: Hardcoded to 3 seconds
- **History**: No fault event storage (current status only)

---

## Quick Reference

```bash
# Check if daemon is working
sudo systemctl is-active psuStatusd
redis-cli -n 6 HGET "PSU_INFO|PSU1" fault_monitoring_updated

# View all PSU info
redis-cli -n 6 HGETALL "PSU_INFO|PSU1"

# Test platform API
python3 -c "from sonic_platform.psu import Psu; print(Psu(0).get_fan_status())"

# Inject test fault
sudo /tmp/test_fan_fault.sh
```