import sys, os, json, time, re
import importlib.util

import importlib.machinery
_fancli_path = os.path.join(os.path.dirname(__file__), '..', 'fancli')
_loader = importlib.machinery.SourceFileLoader('fancli', _fancli_path)
_spec = importlib.util.spec_from_loader('fancli', _loader)
cli = importlib.util.module_from_spec(_spec)

RESET  = '\033[0m'
GREEN  = '\033[32m'
YELLOW = '\033[33m'
RED    = '\033[31m'
CYAN   = '\033[36m'


def reload():
    _spec.loader.exec_module(cli)


def strip_ansi(s):
    return re.sub(r'\033\[[^m]*m', '', s)


class TestColorForTemp:
    def setup_method(self): reload()

    def test_below_60_is_green(self):
        assert cli.color_for_temp(59) == GREEN
        assert cli.color_for_temp(0) == GREEN

    def test_60_to_75_is_yellow(self):
        assert cli.color_for_temp(60) == YELLOW
        assert cli.color_for_temp(75) == YELLOW

    def test_above_75_is_red(self):
        assert cli.color_for_temp(76) == RED
        assert cli.color_for_temp(100) == RED


class TestFormatBar:
    def setup_method(self): reload()

    def test_zero_percent(self):
        bar = strip_ansi(cli.format_bar(0))
        assert '█' not in bar
        assert bar.count('░') == 20

    def test_hundred_percent(self):
        bar = strip_ansi(cli.format_bar(100))
        assert bar.count('█') == 20
        assert '░' not in bar

    def test_fifty_percent(self):
        bar = strip_ansi(cli.format_bar(50))
        assert bar.count('█') == 10
        assert bar.count('░') == 10

    def test_total_length_always_20(self):
        for pct in [0, 10, 33, 50, 66, 99, 100]:
            bar = strip_ansi(cli.format_bar(pct))
            assert len(bar) == 20, f"bar len {len(bar)} for {pct}%"


class TestIsStale:
    def setup_method(self): reload()

    def test_fresh_is_not_stale(self):
        assert cli.is_stale(time.time()) is False

    def test_old_is_stale(self):
        assert cli.is_stale(time.time() - 11) is True

    def test_9s_not_stale(self):
        assert cli.is_stale(time.time() - 9) is False


class TestReadStatus:
    def setup_method(self): reload()

    def test_reads_valid_file(self, tmp_path):
        f = tmp_path / "status.json"
        data = {'mode': 'auto', 'speed_pct': 60, 'cpu_temp': 65,
                'gpu_temp': 72, 'gpu_sensor_ok': True, 'timestamp': time.time()}
        f.write_text(json.dumps(data))
        result = cli.read_status(str(f))
        assert result['speed_pct'] == 60

    def test_missing_file_returns_none(self):
        assert cli.read_status('/nonexistent/status.json') is None

    def test_malformed_returns_none(self, tmp_path):
        f = tmp_path / "status.json"
        f.write_text('{bad}')
        assert cli.read_status(str(f)) is None
