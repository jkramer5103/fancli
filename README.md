# fancli

Linux fan control for the Gigabyte G5 GE.

This tool controls the laptop fans through the embedded controller IO ports. The EC command sequence was reverse engineered from the Windows fan-control software because there was no native Linux control path for this model.

## Hardware

- Tested target: Gigabyte G5 GE
- NVIDIA GPU temperature is read through `nvidia-smi`
- Fan control uses `outb`, provided by the `ioport` package on Debian/Ubuntu

This is hardware-specific low-level control. Use it only on compatible machines and keep an eye on temperatures after installing or changing the curve.

## Install

```bash
sudo apt install ioport
sudo ./install.sh
```

The installer copies the daemon and CLI to `/usr/local/bin`, installs the systemd service, creates `/etc/g5ge-fan/config.json` if missing, and starts `g5ge-fancontrol`.

## Usage

```bash
fancli status
fancli watch
sudo fancli set 70
sudo fancli auto
fancli curve
sudo fancli max
sudo fancli max-stop
```

`set` writes a temporary manual override under `/run/g5ge-fan`. `auto` clears the override and returns to the configured fan curve. `max` stops the daemon and keeps the fan at full speed until `max-stop` restarts automatic control.

## Configuration

Default config path:

```text
/etc/g5ge-fan/config.json
```

Automatic mode with the default curve:

```json
{"mode": "auto"}
```

Custom curve:

```json
{
  "mode": "auto",
  "curve": [[0, 10], [50, 30], [65, 60], [75, 80], [85, 100]]
}
```

Manual config:

```json
{"mode": "manual", "speed": 60}
```

Restart the service after changing persistent config:

```bash
sudo systemctl restart g5ge-fancontrol
```

## Development

```bash
pytest -q
```
