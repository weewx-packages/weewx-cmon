cmon - Computer Monitor
Copyright 2014 Matthew Wall
Distributed under terms of the GPLv3

cmon is a weewx extension to monitor computer metrics such as cpu usage,
memory use, disk space, and ups status.  It saves data to its own database,
then those data can be displayed in weewx reports.  This extension also
includes a sample skin that illustrates how to use the data.

The maintained continuation is 0.21.0. The catalog targets WeeWX 5.5.2–5.6
and Python 3.10–3.14. Collection is primarily Linux-specific; available CPU,
thermal, network and UPS readings depend on the host and permissions.

Installation

Install the published archive with WeeWX 5's extension installer:

```sh
weectl extension install https://github.com/weewx-packages/weewx-cmon/releases/download/v0.21.0/weewx-cmon-0.21.0.zip
```

Use the `weectl` from your WeeWX environment. Add
`--config /path/to/weewx.conf` when the station configuration is not found
automatically. Package installations may require `sudo`; activate the WeeWX
virtual environment for pip installations. Restart your WeeWX service after
configuration, for example `sudo systemctl restart weewx` on systemd.
The installer does not restart it for you.

The installer registers user.cmon.ComputerMonitor in process_services,
installs bin/user/cmon.py, and adds cmon_binding and the cmon.sdb database.
It also creates a report named cmon using skins/cmon. No extra Python
package is required for the base collector. Optional UPS collection requires
the corresponding host utilities and a configured UPS.

Minimal configuration, after installation:

[ComputerMonitor]
    data_binding = cmon_binding
    max_age = 2592000
[StdReport]
    [[cmon]]
        skin = cmon
        enable = true
        HTML_ROOT = /var/www/html/weewx/cmon

Choose an output directory writable by WeeWX and served by your web server.
max_age defaults to 30 days of retention; use None to retain data indefinitely.
Wait for archive records, or run weectl report run cmon to render existing data.

Back up weewx.conf, cmon.sdb and custom skin files before installing an update.
Remove with weectl extension uninstall cmon, then restart WeeWX.

The skin recognizes the following options:

  metrics - which metrics should be displayed in the report
  periods - which time periods should be displayed in the report

For example, to enable all of the metrics and all of the periods, put this
in weewx.conf then restart weewx:

[StdReport]
    [[cmon]]
        [[[Extras]]]
            metrics = rx, battery, cpu, load, disk, mem, net, temp, ups, upsvoltage, upstime
            periods = day, week, month, year

Not every metric is available on every machine.

Independent continuation, 0.21.0, 2026-10-22

This repository continues https://github.com/matthewwall/weewx-cmon from
396546b9b569bcd60a6995feecc4cdd62cac2026, with its full history and license.
It is maintained separately. Use the fixed release archive above.

Inaccessible or vanished mounts are skipped individually. Mount-path octal
escapes are decoded. An existing empty hwmon directory no longer suppresses
thermal_zone0. A malformed hwmon reading does not hide the other sensors.
Temperature fields remain cpu_temp and cpu_tempN, in degrees Celsius.

The Python-2 long traceback in upstream issue #3 is not reproduced on Python 3.
The tests feed large integer counters through the real WeeWX accumulator.
Python 2 is no longer supported by this continuation. Physical Raspberry Pi
sensor access still depends on the host kernel and permissions.
