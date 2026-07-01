#!/usr/bin/env python3
"""G5 GE Fan Control Daemon — controls fans via EC IO ports."""

import json
import logging
import os
import signal
import subprocess
import sys
import time
import glob

DEFAULT_CURVE = [[0, 10], [50, 30], [65, 60], [75, 80], [85, 100]]
CONFIG_PATH = '/etc/g5ge-fan/config.json'
OVERRIDE_PATH = '/run/g5ge-fan/override.json'
STATUS_PATH = '/run/g5ge-fan/status.json'
CYCLE_SECONDS = 2


def interpolate_curve(curve, temp):
    """Linear interpolation of fan speed % from curve at given temp."""
    if temp <= curve[0][0]:
        return curve[0][1]
    if temp >= curve[-1][0]:
        return curve[-1][1]
    for i in range(len(curve) - 1):
        t0, s0 = curve[i]
        t1, s1 = curve[i + 1]
        if t0 <= temp <= t1:
            frac = (temp - t0) / (t1 - t0)
            return s0 + frac * (s1 - s0)
    return curve[-1][1]


def load_config(path):
    """Load and parse config/override JSON. Returns dict or None on error."""
    try:
        with open(path) as f:
            data = json.load(f)
        if 'mode' not in data:
            return None
        if data['mode'] == 'auto':
            data.setdefault('curve', DEFAULT_CURVE)
        return data
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, Exception):
        return None


def pct_to_raw(percent):
    """Convert 0-100% to 0-255 raw EC value."""
    return round(percent * 255 / 100)


def read_cpu_temp(glob_pattern=None):
    """Return max CPU temp in °C across all thermal zones, or None."""
    if glob_pattern is None:
        glob_pattern = '/sys/class/thermal/thermal_zone*/temp'
    paths = glob.glob(glob_pattern)
    if not paths:
        return None
    temps = []
    for p in paths:
        try:
            with open(p) as f:
                temps.append(int(f.read().strip()) / 1000.0)
        except (OSError, ValueError):
            continue
    return max(temps) if temps else None


def read_gpu_temp():
    """Run nvidia-smi and return GPU temp as int, or None on failure."""
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=temperature.gpu', '--format=csv,noheader'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return None
        return int(result.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, Exception):
        return None


class GpuState:
    """Stateful tracker for GPU temperature with fallback."""
    def __init__(self):
        self.last_temp = 0
        self.sensor_ok = True
        self.error_logged = False


def read_gpu_with_fallback(state):
    """Read GPU temp, falling back to last known value on failure.
    Returns (temp, sensor_ok). Updates state in-place."""
    temp = read_gpu_temp()
    if temp is not None:
        state.last_temp = temp
        state.sensor_ok = True
        state.error_logged = False
        return temp, True
    else:
        state.sensor_ok = False
        return state.last_temp, False


def send_fan_speeds(cpu_raw, gpu_raw):
    """Send outb commands to set fan speed via EC.
    Register 0x01 controls the fan (GPU follows CPU on this platform).
    """
    sequence = [
        ['outb', '0x66', '0x99'],        # unlock EC
        ['outb', '0x62', '0x01'],         # select fan register
        ['outb', '0x62', f'0x{cpu_raw:02X}'],  # write speed
    ]
    for cmd in sequence:
        subprocess.run(cmd, check=True)
        time.sleep(0.01)  # 10ms between calls for EC timing


def write_status(path, mode, speed_pct, cpu_temp, gpu_temp, gpu_sensor_ok):
    """Atomically write status.json."""
    data = {
        'mode': mode,
        'speed_pct': round(speed_pct),
        'cpu_temp': round(cpu_temp) if cpu_temp is not None else 0,
        'gpu_temp': round(gpu_temp),
        'gpu_sensor_ok': gpu_sensor_ok,
        'timestamp': time.time(),
    }
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f)
        f.flush()
        os.fsync(f.fileno())
    os.rename(tmp, path)
    os.chmod(path, 0o644)


def get_active_config():
    """Load override if present, else load config. Returns (config_dict, source)."""
    override = load_config(OVERRIDE_PATH)
    if override is not None:
        return override, 'override'
    config = load_config(CONFIG_PATH)
    if config is not None:
        return config, 'config'
    logging.warning("No valid config found; using auto mode with default curve")
    return {'mode': 'auto', 'curve': DEFAULT_CURVE}, 'default'


def run_daemon():
    """Main daemon loop."""
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s %(levelname)s %(message)s',
        stream=sys.stdout,
    )
    logging.info("g5ge-fandaemon starting")

    gpu_state = GpuState()
    running = True

    def handle_sigterm(signum, frame):
        nonlocal running
        logging.info("Received SIGTERM, shutting down")
        running = False

    signal.signal(signal.SIGTERM, handle_sigterm)

    while running:
        cycle_start = time.monotonic()

        config, source = get_active_config()
        mode = config.get('mode', 'auto')

        cpu_temp = read_cpu_temp()
        if cpu_temp is None:
            logging.error("Could not read CPU temperature")
            cpu_temp = 0

        gpu_temp, gpu_ok = read_gpu_with_fallback(gpu_state)
        if not gpu_ok and not gpu_state.error_logged:
            logging.error("nvidia-smi failed; using last known GPU temp=%d", gpu_temp)
            gpu_state.error_logged = True
        elif not gpu_ok:
            logging.debug("nvidia-smi still failing; gpu_temp=%d (cached)", gpu_temp)

        if mode == 'manual':
            speed_pct = float(config.get('speed', 50))
        else:
            temp_input = max(cpu_temp, gpu_temp)
            curve = config.get('curve', DEFAULT_CURVE)
            speed_pct = interpolate_curve(curve, temp_input)

        speed_pct = max(0.0, min(100.0, speed_pct))
        raw = pct_to_raw(speed_pct)

        logging.debug(
            "mode=%s source=%s cpu=%.1f gpu=%d speed=%.1f%% raw=%d",
            mode, source, cpu_temp, gpu_temp, speed_pct, raw
        )

        try:
            send_fan_speeds(raw, raw)
        except subprocess.CalledProcessError as e:
            logging.error("outb failed: %s", e)
        except FileNotFoundError:
            logging.error("outb binary not found — install ioport package")

        try:
            write_status(STATUS_PATH, mode, speed_pct, cpu_temp, gpu_temp, gpu_ok)
        except OSError as e:
            logging.error("Failed to write status: %s", e)

        elapsed = time.monotonic() - cycle_start
        sleep_for = max(0, CYCLE_SECONDS - elapsed)
        if running:
            time.sleep(sleep_for)

    logging.info("g5ge-fandaemon stopped")


if __name__ == '__main__':
    run_daemon()
