import sys, os, json
import importlib.util
from unittest.mock import patch, MagicMock
import pytest

import importlib.machinery
_fancli_path = os.path.join(os.path.dirname(__file__), '..', 'fancli')
_loader = importlib.machinery.SourceFileLoader('fancli', _fancli_path)
_spec = importlib.util.spec_from_loader('fancli', _loader)
cli = importlib.util.module_from_spec(_spec)


def reload():
    _spec.loader.exec_module(cli)


class TestCmdSet:
    def setup_method(self): reload()

    def test_writes_override_json(self, tmp_path):
        override_path = str(tmp_path / "override.json")
        with patch.object(cli, 'OVERRIDE_PATH', override_path), \
             patch.object(cli, 'RUN_DIR', str(tmp_path)):
            args = MagicMock()
            args.percent = 75
            cli.cmd_set(args)
        with open(override_path) as f:
            data = json.load(f)
        assert data == {'mode': 'manual', 'speed': 75}

    def test_invalid_percent_exits_1(self):
        args = MagicMock()
        args.percent = 150
        with pytest.raises(SystemExit) as exc:
            cli.cmd_set(args)
        assert exc.value.code == 1

    def test_prints_confirmation(self, tmp_path, capsys):
        override_path = str(tmp_path / "override.json")
        with patch.object(cli, 'OVERRIDE_PATH', override_path), \
             patch.object(cli, 'RUN_DIR', str(tmp_path)):
            args = MagicMock()
            args.percent = 50
            cli.cmd_set(args)
        out = capsys.readouterr().out
        assert "Override set: manual at 50%" in out


class TestCmdAuto:
    def setup_method(self): reload()

    def test_removes_override_file(self, tmp_path):
        override_path = str(tmp_path / "override.json")
        with open(override_path, 'w') as f:
            json.dump({'mode': 'manual', 'speed': 80}, f)
        with patch.object(cli, 'OVERRIDE_PATH', override_path):
            cli.cmd_auto(MagicMock())
        assert not os.path.exists(override_path)

    def test_no_op_when_no_override(self, tmp_path, capsys):
        override_path = str(tmp_path / "override.json")
        with patch.object(cli, 'OVERRIDE_PATH', override_path):
            cli.cmd_auto(MagicMock())
        out = capsys.readouterr().out
        assert "Override cleared" in out

    def test_permission_error_exits_1(self, tmp_path):
        override_path = str(tmp_path / "override.json")
        with open(override_path, 'w') as f:
            f.write('{}')
        with patch.object(cli, 'OVERRIDE_PATH', override_path), \
             patch('os.remove', side_effect=PermissionError):
            with pytest.raises(SystemExit) as exc:
                cli.cmd_auto(MagicMock())
        assert exc.value.code == 1


class TestGetActiveCurveInfo:
    def setup_method(self): reload()

    def test_auto_override_uses_override_curve(self, tmp_path):
        override = tmp_path / "override.json"
        override.write_text('{"mode": "auto", "curve": [[0,5],[100,90]]}')
        config = tmp_path / "config.json"
        config.write_text('{"mode": "auto", "curve": [[0,10],[100,100]]}')
        with patch.object(cli, 'OVERRIDE_PATH', str(override)), \
             patch.object(cli, 'CONFIG_PATH', str(config)):
            curve, manual_speed, note = cli.get_active_curve_info()
        assert curve == [[0, 5], [100, 90]]
        assert manual_speed is None

    def test_malformed_override_falls_through_to_config(self, tmp_path):
        override = tmp_path / "override.json"
        override.write_text('{bad json}')
        config = tmp_path / "config.json"
        config.write_text('{"mode": "auto", "curve": [[0,10],[100,100]]}')
        with patch.object(cli, 'OVERRIDE_PATH', str(override)), \
             patch.object(cli, 'CONFIG_PATH', str(config)):
            curve, manual_speed, note = cli.get_active_curve_info()
        assert curve == [[0, 10], [100, 100]]

    def test_manual_override_shows_config_curve_with_speed(self, tmp_path):
        override = tmp_path / "override.json"
        override.write_text('{"mode": "manual", "speed": 70}')
        config = tmp_path / "config.json"
        config.write_text('{"mode": "auto", "curve": [[0,10],[100,100]]}')
        with patch.object(cli, 'OVERRIDE_PATH', str(override)), \
             patch.object(cli, 'CONFIG_PATH', str(config)):
            curve, manual_speed, note = cli.get_active_curve_info()
        assert curve == [[0, 10], [100, 100]]
        assert manual_speed == 70

    def test_no_files_uses_default_curve(self, tmp_path):
        with patch.object(cli, 'OVERRIDE_PATH', str(tmp_path / 'o.json')), \
             patch.object(cli, 'CONFIG_PATH', str(tmp_path / 'c.json')):
            curve, manual_speed, note = cli.get_active_curve_info()
        assert curve == cli.DEFAULT_CURVE
        assert "default" in note.lower()
