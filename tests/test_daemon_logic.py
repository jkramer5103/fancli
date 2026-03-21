import sys, os
import importlib.util
from unittest.mock import patch, MagicMock

_spec = importlib.util.spec_from_file_location(
    "daemon", os.path.join(os.path.dirname(__file__), '..', 'g5ge-fandaemon.py'))
daemon = importlib.util.module_from_spec(_spec)

DEFAULT_CURVE = [[0, 10], [50, 30], [65, 60], [75, 80], [85, 100]]


def reload():
    _spec.loader.exec_module(daemon)


class TestInterpolateCurve:
    def setup_method(self): reload()

    def test_below_range_uses_first_point(self):
        assert daemon.interpolate_curve(DEFAULT_CURVE, 0) == 10

    def test_above_range_uses_last_point(self):
        assert daemon.interpolate_curve(DEFAULT_CURVE, 100) == 100

    def test_exact_point(self):
        assert daemon.interpolate_curve(DEFAULT_CURVE, 50) == 30
        assert daemon.interpolate_curve(DEFAULT_CURVE, 65) == 60

    def test_interpolated_midpoint(self):
        # Between [50,30] and [65,60]: at temp=57.5, speed=45.0
        result = daemon.interpolate_curve(DEFAULT_CURVE, 57.5)
        assert abs(result - 45.0) < 0.1

    def test_single_point_curve(self):
        assert daemon.interpolate_curve([[50, 40]], 0) == 40
        assert daemon.interpolate_curve([[50, 40]], 100) == 40


class TestLoadConfig:
    def setup_method(self): reload()

    def test_auto_no_curve(self, tmp_path):
        f = tmp_path / "config.json"
        f.write_text('{"mode": "auto"}')
        cfg = daemon.load_config(str(f))
        assert cfg['mode'] == 'auto'
        assert cfg['curve'] == DEFAULT_CURVE

    def test_auto_with_custom_curve(self, tmp_path):
        f = tmp_path / "config.json"
        f.write_text('{"mode": "auto", "curve": [[0,5],[100,100]]}')
        cfg = daemon.load_config(str(f))
        assert cfg['curve'] == [[0, 5], [100, 100]]

    def test_manual(self, tmp_path):
        f = tmp_path / "config.json"
        f.write_text('{"mode": "manual", "speed": 80}')
        cfg = daemon.load_config(str(f))
        assert cfg['mode'] == 'manual'
        assert cfg['speed'] == 80

    def test_unknown_keys_ignored(self, tmp_path):
        f = tmp_path / "config.json"
        f.write_text('{"mode": "auto", "foo": "bar"}')
        cfg = daemon.load_config(str(f))
        assert cfg['mode'] == 'auto'

    def test_missing_file_returns_none(self):
        assert daemon.load_config('/nonexistent/path.json') is None

    def test_malformed_json_returns_none(self, tmp_path):
        f = tmp_path / "config.json"
        f.write_text('{bad json}')
        assert daemon.load_config(str(f)) is None


class TestSpeedConversion:
    def setup_method(self): reload()

    def test_zero_percent(self):
        assert daemon.pct_to_raw(0) == 0

    def test_hundred_percent(self):
        assert daemon.pct_to_raw(100) == 255

    def test_fifty_percent(self):
        assert daemon.pct_to_raw(50) == 128  # round(50*255/100)


class TestReadCpuTemp:
    def setup_method(self): reload()

    def test_returns_max_across_zones(self, tmp_path):
        for i, temp_mc in enumerate([45000, 72000, 38000]):
            zone = tmp_path / f"thermal_zone{i}"
            zone.mkdir()
            (zone / "temp").write_text(str(temp_mc))
        result = daemon.read_cpu_temp(str(tmp_path) + "/thermal_zone*/temp")
        assert result == 72.0

    def test_returns_none_when_no_zones(self, tmp_path):
        result = daemon.read_cpu_temp(str(tmp_path) + "/thermal_zone*/temp")
        assert result is None


class TestReadGpuTemp:
    def setup_method(self): reload()

    def test_success_returns_int(self):
        mock_result = MagicMock(returncode=0, stdout="72\n")
        with patch('subprocess.run', return_value=mock_result):
            assert daemon.read_gpu_temp() == 72

    def test_nonzero_exit_returns_none(self):
        with patch('subprocess.run', return_value=MagicMock(returncode=1, stdout="")):
            assert daemon.read_gpu_temp() is None

    def test_non_integer_output_returns_none(self):
        with patch('subprocess.run', return_value=MagicMock(returncode=0, stdout="N/A\n")):
            assert daemon.read_gpu_temp() is None

    def test_exception_returns_none(self):
        with patch('subprocess.run', side_effect=FileNotFoundError):
            assert daemon.read_gpu_temp() is None


class TestGpuFallbackState:
    def setup_method(self): reload()

    def test_first_failure_returns_zero(self):
        state = daemon.GpuState()
        with patch('subprocess.run', side_effect=FileNotFoundError):
            temp, ok = daemon.read_gpu_with_fallback(state)
        assert temp == 0
        assert ok is False

    def test_success_after_failure_resets_state(self):
        state = daemon.GpuState()
        with patch('subprocess.run', return_value=MagicMock(returncode=1, stdout="")):
            daemon.read_gpu_with_fallback(state)
        with patch('subprocess.run', return_value=MagicMock(returncode=0, stdout="65\n")):
            temp, ok = daemon.read_gpu_with_fallback(state)
        assert temp == 65
        assert ok is True
        assert state.error_logged is False

    def test_uses_last_known_temp_on_failure(self):
        state = daemon.GpuState()
        with patch('subprocess.run', return_value=MagicMock(returncode=0, stdout="70\n")):
            daemon.read_gpu_with_fallback(state)
        with patch('subprocess.run', return_value=MagicMock(returncode=1, stdout="")):
            temp, ok = daemon.read_gpu_with_fallback(state)
        assert temp == 70
        assert ok is False
