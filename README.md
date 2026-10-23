# cmon

cmon records metrics of the computer running WeeWX: CPU usage, load, memory,
swap, disk space, network traffic and CPU temperature. It saves them to its own
database, not to the weather archive. A small `cmon` skin plots them.

Independent continuation of
[matthewwall/weewx-cmon](https://github.com/matthewwall/weewx-cmon), continued
from commit `396546b` with its full history.

## Requirements

- Linux. The collector reads `/proc` and `/sys` and needs no Python package
  beyond WeeWX.
- On macOS, `psutil` in the Python environment running WeeWX:

  ```sh
  python -m pip install psutil
  ```

Which readings exist depends on the host, its kernel and the permissions of
the WeeWX user.

## Installation

Install `cmon` from the [WeeWX packages catalog](https://github.com/weewx-packages/catalog/blob/main/packages/cmon.md).
The catalog page lists the current release, its WeeWX and Python
requirements, and the install, update and removal commands.

The installer registers `user.cmon.ComputerMonitor` in `process_services` and
copies `bin/user/cmon.py` and `skins/cmon`. It adds `[ComputerMonitor]`, the
`cmon_binding` data binding, the `cmon_sqlite` database with the file
`cmon.sdb`, and a report `cmon`. The report writes to the `cmon` subdirectory
of `[StdReport] HTML_ROOT`.

After the restart, the service stores its first record at the second archive
interval, because CPU and network values are differences between two samples. To render the page before the next report cycle, run
`weectl report run cmon`.

## Configuration

What the installer adds to `weewx.conf`:

```ini
[ComputerMonitor]
    data_binding = cmon_binding

[DataBindings]
    [[cmon_binding]]
        database = cmon_sqlite
        table_name = archive
        manager = weewx.manager.DaySummaryManager
        schema = user.cmon.schema

[Databases]
    [[cmon_sqlite]]
        database_type = SQLite
        database_name = cmon.sdb

[StdReport]
    [[cmon]]
        skin = cmon
        HTML_ROOT = cmon
```

Options in `[ComputerMonitor]`:

| Option | Default | Meaning |
| --- | --- | --- |
| `data_binding` | `cmon_binding` | Binding of the database cmon writes to. |
| `max_age` | `2592000` | Records older than this many seconds are deleted. `None` keeps all records. |
| `ignored_mounts` | `/lib/init/rw, /proc, /sys, /dev, /afs, /mit, /run, /var/lib/nfs` | Mount points starting with one of these paths are skipped. Setting the option replaces the whole list. Network mounts with `:` in the device name are always skipped. |
| `hardware` | none | `apcups` reads a UPS through `/sbin/apcaccess`, `rpi` reads `/opt/vc/bin/vcgencmd`. See Limitations. |

### Stored values

The default schema `user.cmon.schema` stores these columns. The collector
reads more, for example every network interface and every mount, but only
columns in the schema are saved.

| Columns | Unit |
| --- | --- |
| `mem_total`, `mem_free`, `mem_used`, `swap_total`, `swap_free`, `swap_used` | kB on Linux |
| `cpu_user`, `cpu_nice`, `cpu_system`, `cpu_idle`, `cpu_iowait`, `cpu_irq`, `cpu_softirq` | CPU time ticks since the previous sample |
| `load1`, `load5`, `load15` | load average |
| `proc_active`, `proc_total` | number of processes |
| `cpu_temp`, `cpu_temp1` to `cpu_temp4` | °C |
| `net_eth0_*`, `net_wlan0_*` with `rbytes`, `rpackets`, `rerrs`, `rdrop`, `tbytes`, `tpackets`, `terrs`, `tdrop` | difference since the previous sample |
| `disk_root_*`, `disk_home_*` with `total`, `free`, `used` | kB |
| `ups_temp`, `ups_load`, `ups_charge`, `ups_voltage`, `ups_time` | numbers from `apcaccess`, see Limitations |

`cpu_temp` comes from `/sys/class/thermal/thermal_zone0/temp`. `cpu_tempN`
comes from the `tempN_input` files under `/sys/class/hwmon/hwmon*`. Disk
columns are named after the mount point, with `/` replaced by `_`; the root
file system is `disk_root`. Mounts that cannot be read are skipped.

To store other interfaces or mounts, give the binding its own schema. The
module docstring in [bin/user/cmon.py](bin/user/cmon.py) shows an inline
`[[[schema]]]` and a schema defined in `user/extensions.py`. The columns of an
existing `cmon.sdb` must match the configured schema. Otherwise the service
stops WeeWX with `cmon schema mismatch`. After a schema change, start with a
new database file.

### The cmon report

The skin plots from `cmon_binding`. The metrics `rx` and `battery` plot the
weather station's `rxCheckPercent` and battery status from `wx_binding`. The
page offers check boxes for the metrics and periods listed in `[Extras]`:

| Option | Default |
| --- | --- |
| `metrics` | `rx, battery, cpu, load, disk, mem, net, temp` |
| `periods` | `day, week, month, year` |

To show fewer plots, set them in `weewx.conf` and restart WeeWX:

```ini
[StdReport]
    [[cmon]]
        [[[Extras]]]
            metrics = cpu, load, mem, disk
            periods = day, week
```

The plots `ups`, `upsvoltage` and `upstime` are commented out in
[skins/cmon/skin.conf](skins/cmon/skin.conf). Listing them in `metrics` alone
produces missing images.

The `net` plot shows `eth0` and the `disk` plot shows `/`. On hosts with other
interface names the `net` plot stays empty.

### Running cmon as the station driver

`cmon.py` can also act as the station driver. The readings then go into the
LOOP packets of the main station, and only columns of the weather archive's
schema are stored.

```ini
[Station]
    station_type = ComputerMonitor

[ComputerMonitor]
    driver = user.cmon
    polling_interval = 10
```

`polling_interval` is the time between samples in seconds, default `10`.
`ignored_mounts` and `hardware` work as in the service.

## Limitations

- `hardware = apcups` and `hardware = rpi` raise `TypeError` on Python 3,
  because the command output is read as bytes. The error is not caught, so
  WeeWX stops at the first sample.
- A single value for `ignored_mounts`, such as `ignored_mounts = /proc`, is
  read as a string, not a list. Every mount is then skipped. Use at least two
  comma-separated paths.
- Mounts are read per device from `/proc/mounts`. When one device is mounted
  at several places, for example with bind mounts, only its last mount point
  is recorded. `disk_root` can be missing for that reason.
- On macOS, memory and swap values are in bytes, not kB. Load and
  temperature are not collected there.
- Other systems, including the BSDs, are not supported. The service then
  stops WeeWX at startup.
- The tests use fixture files. Readings on a real host depend on its kernel
  and are not verified by them.

## Development

```sh
python -m pytest -q tests
```

Run it in an environment with WeeWX and pytest. The tests use fixture `/proc`
and `/sys` trees and feed large integer counters through the WeeWX
accumulator.

## License

Copyright 2014 Matthew Wall. Distributed under the terms of the GPLv3, see
[license](license). The continuation keeps this license.
