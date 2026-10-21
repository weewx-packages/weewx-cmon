cmon - Computer Monitor
Copyright 2014 Matthew Wall
Distributed under terms of the GPLv3

cmon is a weewx extension to monitor computer metrics such as cpu usage,
memory use, disk space, and ups status.  It saves data to its own database,
then those data can be displayed in weewx reports.  This extension also
includes a sample skin that illustrates how to use the data.

Installation instructions:

1) run the installer:

wee_extension --install weewx-cmon.tgz

2) restart weewx:

sudo /etc/init.d/weewx stop
sudo /etc/init.d/weewx start

This will result in a skin called cmon with a single web page that illustrates
how to use the monitoring data.  See comments in cmon.py for customization
options.

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
It is maintained separately. Install with WeeWX 5:

weectl extension install https://github.com/weewx-packages/weewx-cmon/archive/refs/tags/v0.21.0.zip

Inaccessible or vanished mounts are skipped individually. Mount-path octal
escapes are decoded. An existing empty hwmon directory no longer suppresses
thermal_zone0. A malformed hwmon reading does not hide the other sensors.
Temperature fields remain cpu_temp and cpu_tempN, in degrees Celsius.

The Python-2 long traceback in upstream issue #3 is not reproduced on Python 3.
The tests feed large integer counters through the real WeeWX accumulator.
Python 2 is no longer supported by this continuation. Physical Raspberry Pi
sensor access still depends on the host kernel and permissions.
