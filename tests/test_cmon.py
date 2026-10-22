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
