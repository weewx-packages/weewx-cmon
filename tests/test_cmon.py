import importlib.util
from pathlib import Path
import os

import pytest
import weewx.accum
from weeutil.weeutil import TimeSpan

SPEC = importlib.util.spec_from_file_location('cmon', Path(__file__).parents[1] / 'bin/user/cmon.py')
cmon = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cmon)


@pytest.fixture
def collector(tmp_path, monkeypatch):
    proc, sys = tmp_path / 'proc', tmp_path / 'sys'
    proc.mkdir()
    sys.mkdir()
    monkeypatch.setattr(cmon.LinuxCollector, 'PROC_ROOT', str(proc), raising=False)
    monkeypatch.setattr(cmon.LinuxCollector, 'SYS_ROOT', str(sys), raising=False)
    (proc / 'cpuinfo').write_text('model name: fixture CPU\n')
    (proc / 'meminfo').write_text('MemTotal: 10000000000 kB\nMemFree: 10 kB\n')
    (proc / 'stat').write_text('cpu 100 200 300 400 0 0 0\n')
    (proc / 'loadavg').write_text('0.5 0.4 0.3 1/10 123\n')
    (proc / 'mounts').write_text('')
    return cmon.LinuxCollector([], []), proc, sys


def test_empty_hwmon_does_not_hide_thermal_zone(collector):
    sensor, proc, sys = collector
    (sys / 'class/hwmon/hwmon0/device').mkdir(parents=True)
    zone = sys / 'class/thermal/thermal_zone0'
    zone.mkdir(parents=True)
    (zone / 'temp').write_text('42500\n')
    assert sensor.get_data(100)['cpu_temp'] == 42.5


def test_bad_hwmon_sensor_does_not_hide_other_sensor(collector):
    sensor, proc, sys = collector
    hwmon = sys / 'class/hwmon/hwmon0/device'
    hwmon.mkdir(parents=True)
    (hwmon / 'temp1_input').write_text('bad\n')
    (hwmon / 'temp2_input').write_text('-1250\n')
    (hwmon / 'fan1_input').write_text('2000\n')
    record = sensor.get_data(100)
    assert record['cpu_temp2'] == -1.25
    assert 'cpu_fan1' not in record


def test_denied_mount_and_disappearing_mount(collector, tmp_path):
    sensor, proc, sys = collector
    denied = tmp_path / 'denied'
    child = denied / 'child'
    child.mkdir(parents=True)
    denied.chmod(0)
    missing = tmp_path / 'gone'
    available = tmp_path / 'mounted space'
    available.mkdir()
    escaped = str(available).replace(' ', '\\040')
    (proc / 'mounts').write_text('a %s ext4 rw 0 0\nb %s ext4 rw 0 0\nc %s ext4 rw 0 0\n' % (child, missing, escaped))
    try:
        with pytest.raises(PermissionError):
            os.statvfs(child)
        record = sensor.get_data(100)
    finally:
        denied.chmod(0o700)
    assert record['disk' + str(available).replace('/', '_') + '_total'] > 0
    assert 'disk' + str(child).replace('/', '_') + '_total' not in record


def test_large_counters_work_with_current_weewx(collector):
    sensor, proc, sys = collector
    record = sensor.get_data(100)
    assert record['mem_total'] == 10000000000
    record['interval'] = 5
    weewx.accum.initialize({})
    accumulator = weewx.accum.Accum(TimeSpan(0, 100))
    accumulator.addRecord(record)
    assert accumulator['mem_total'].max == 10000000000


def test_hwmon_without_device_subdirectory(collector):
    sensor, proc, sys = collector
    hwmon = sys / 'class/hwmon/hwmon2'
    hwmon.mkdir(parents=True)
    (hwmon / 'temp1_input').write_text('31000\n')
    assert sensor.get_data(100)['cpu_temp1'] == 31.0


def test_service_keeps_existing_database_values(collector, tmp_path, monkeypatch):
    import configobj
    from types import SimpleNamespace
    import weewx
    import weewx.manager

    sensor, proc, sys = collector
    monkeypatch.setattr(cmon, 'get_collector', lambda *args: sensor)
    config = configobj.ConfigObj({
        'ComputerMonitor': {'max_age': None},
        'DataBindings': {'cmon_binding': {'database': 'cmon', 'table_name': 'archive',
            'manager': 'weewx.manager.DaySummaryManager', 'schema': dict(cmon.schema)}},
        'Databases': {'cmon': {'driver': 'weedb.sqlite',
            'database_name': str(tmp_path / 'historical.sdb')}}})
    binder = weewx.manager.DBBinder(config)
    try:
        manager = binder.get_manager('cmon_binding', initialize=True)
        manager.addRecord({'dateTime': 1000000000, 'usUnits': weewx.METRIC, 'interval': 5,
            'cpu_temp': 42.5, 'cpu_temp1': 30.25, 'mem_total': 10000000000})
        before = manager.getRecord(1000000000)
        service = cmon.ComputerMonitor(SimpleNamespace(db_binder=binder,
            bind=lambda *args: None), config)
        service.save_data(service.get_data(1000000300, 1000000000))
        assert manager.getRecord(1000000000) == before
        assert manager.getRecord(1000000300)['usUnits'] == weewx.METRIC
        assert manager.getRecord(1000000300)['mem_total'] == 10000000000
    finally:
        binder.close()


def test_apcups_output_is_parsed_as_text(monkeypatch):
    import subprocess
    output = 'printf "LOADPCT  :  12.0 Percent\\nTIMELEFT :  47.0 Minutes\\n"'
    monkeypatch.setattr(cmon, 'Popen', lambda cmd, **kw: subprocess.Popen(output, **kw))
    assert cmon.Collector._get_apcups_info() == {'ups_load': 12.0, 'ups_time': 47.0}


def test_rpi_output_is_parsed_as_text(tmp_path, monkeypatch):
    vcgencmd = tmp_path / 'vcgencmd'
    vcgencmd.write_text('#!/bin/sh\necho "temp=42.8\'C"\n')
    vcgencmd.chmod(0o755)
    monkeypatch.setattr(cmon.Collector, '_RPI_VCGENCMD', str(vcgencmd))
    assert cmon.Collector._get_rpi_info()['core_temp'] == 42.8


def test_single_ignored_mount_is_a_list(collector, tmp_path):
    sensor, proc, sys = collector
    (proc / 'mounts').write_text('proc /proc proc rw 0 0\n/dev/sda1 %s ext4 rw 0 0\n' % tmp_path)
    driver = cmon.ComputerMonitorDriver(ignored_mounts='/proc')
    record = driver.collector.get_data(100)
    assert 'disk' + str(tmp_path).replace('/', '_') + '_total' in record
    assert 'disk_proc_total' not in record


def test_device_mounted_twice_records_both_mount_points(collector, tmp_path):
    sensor, proc, sys = collector
    first, second = tmp_path / 'first', tmp_path / 'second'
    first.mkdir()
    second.mkdir()
    (proc / 'mounts').write_text('/dev/sda1 %s ext4 rw 0 0\n/dev/sda1 %s ext4 rw 0 0\n' % (first, second))
    record = sensor.get_data(100)
    assert 'disk' + str(first).replace('/', '_') + '_total' in record
    assert 'disk' + str(second).replace('/', '_') + '_total' in record


def test_unsupported_system_is_reported(monkeypatch):
    monkeypatch.setattr(cmon.platform, 'system', lambda: 'BSD')
    with pytest.raises(Exception, match='unsupported system BSD'):
        cmon.get_collector()


def test_macos_memory_is_in_kb(monkeypatch):
    import sys
    from types import SimpleNamespace
    memory = SimpleNamespace(total=2048, free=1024, used=1024, available=1024,
                             active=1024, inactive=0, wired=0)
    swap = SimpleNamespace(total=4096, free=4096, used=0, sin=0, sout=0)
    psutil = SimpleNamespace(virtual_memory=lambda: memory, swap_memory=lambda: swap,
                             cpu_count=lambda: 1, cpu_times=lambda: SimpleNamespace(),
                             net_io_counters=lambda pernic: {}, disk_partitions=lambda: [])
    monkeypatch.setitem(sys.modules, 'psutil', psutil)
    record = cmon.MacOSXCollector([], []).get_data(100)
    assert (record['mem_total'], record['mem_free'], record['swap_total']) == (2, 1, 4)


def test_main_runs_without_options():
    import subprocess
    import sys
    path = Path(__file__).parents[1] / 'bin/user/cmon.py'
    result = subprocess.run([sys.executable, str(path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_skin_has_no_hard_coded_version():
    import configobj
    skin = Path(__file__).parents[1] / 'skins/cmon'
    assert 'version' not in configobj.ConfigObj(str(skin / 'skin.conf'))['Extras']
    assert '$Extras.version' not in (skin / 'index.html.tmpl').read_text()


def test_rpi_memory_comes_from_get_mem(tmp_path, monkeypatch):
    vcgencmd = tmp_path / 'vcgencmd'
    vcgencmd.write_text('#!/bin/sh\n'
                        'case "$1 $2" in\n'
                        '  "measure_temp ") echo "temp=42.8\'C" ;;\n'
                        '  "get_mem arm") echo "arm=948M" ;;\n'
                        '  "get_mem gpu") echo "gpu=76M" ;;\n'
                        'esac\n')
    vcgencmd.chmod(0o755)
    monkeypatch.setattr(cmon.Collector, '_RPI_VCGENCMD', str(vcgencmd))
    record = cmon.Collector._get_rpi_info()
    assert record['arm_mem'] == 948 and record['gpu_mem'] == 76


def test_apcups_battery_and_output_voltage_do_not_overwrite(monkeypatch):
    import subprocess
    # Order as in the Smart-UPS example of the apcupsd manual.
    output = 'printf "OUTPUTV  : 232.7 Volts\\nBATTV    : 27.7 Volts\\n"'
    monkeypatch.setattr(cmon, 'Popen', lambda cmd, **kw: subprocess.Popen(output, **kw))
    assert cmon.Collector._get_apcups_info() == {'ups_voltage': 27.7, 'ups_output_voltage': 232.7}


def test_missing_apcaccess_is_logged(monkeypatch, caplog):
    import subprocess
    monkeypatch.setattr(cmon, 'Popen',
                        lambda cmd, **kw: subprocess.Popen('/nonexistent/apcaccess', stderr=subprocess.DEVNULL, **kw))
    assert cmon.Collector._get_apcups_info() == {}
    assert 'apcups_info failed: /sbin/apcaccess exited with status 127' in caplog.text


def test_rpi_voltages_fill_schema_columns(tmp_path, monkeypatch):
    vcgencmd = tmp_path / 'vcgencmd'
    vcgencmd.write_text('#!/bin/sh\n'
                        'case "$1 $2" in\n'
                        '  "measure_temp ") echo "temp=42.8\'C" ;;\n'
                        '  "measure_volts core") echo "volt=1.2000V" ;;\n'
                        '  "measure_volts sdram_c") echo "volt=1.2500V" ;;\n'
                        '  "measure_volts sdram_i") echo "volt=1.2600V" ;;\n'
                        '  "measure_volts sdram_p") echo "volt=1.2700V" ;;\n'
                        'esac\n')
    vcgencmd.chmod(0o755)
    monkeypatch.setattr(cmon.Collector, '_RPI_VCGENCMD', str(vcgencmd))
    record = cmon.Collector._get_rpi_info()
    assert (record['core_volt'], record['core_sdram_c'], record['core_sdram_i'],
            record['core_sdram_p']) == (1.2, 1.25, 1.26, 1.27)


def test_vcgencmd_is_found_on_path(tmp_path, monkeypatch):
    vcgencmd = tmp_path / 'vcgencmd'
    vcgencmd.write_text('#!/bin/sh\n')
    vcgencmd.chmod(0o755)
    monkeypatch.setenv('PATH', str(tmp_path))
    module = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(module)
    assert module.Collector._RPI_VCGENCMD == str(vcgencmd)
