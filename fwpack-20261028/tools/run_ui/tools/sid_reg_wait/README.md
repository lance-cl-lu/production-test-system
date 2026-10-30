# sid_reg_wait

Resets a sid_smartac device (WLE and WBA) and waits for the WBA to report that it is registered with Sidewalk. A station test step after flashing. Uses [stflash's stlink module](../stflash/README.md#shared-st-link-module-stlinkpy) for the ST-Links and needs pyserial for the logs.

## Wiring

The device is on two ST-Links. Each ST-Link's virtual COM port (VCP) is wired to the log UART of its MCU: WBA USART1 and WLE USART2, both 115200 8N1. NRST must be wired too, for the reset.

```sh
pip install -r smac_tools/run_ui/requirements.txt     # pyserial
smac_tools/run_ui/tools/sid_reg_wait/sid_reg_wait.py
```

## What it does

1. Finds which ST-Link is on which MCU, like stflash (or checks `--wle-sn` / `--wba-sn`), but connecting under reset only: hot-plug sometimes fails to reach the MCU.
2. Finds each ST-Link's VCP: the serial port whose USB serial number is the ST-Link serial. `--wba-port` / `--wle-port` override it. A missing WBA port is an error; a missing WLE port only means the WLE log is not shown.
3. Opens the ports, then resets the WLE and then the WBA through NRST (`mode=UR -hardRst`), so no boot output is missed.
4. Prints every log line as `[WBA-UART] ...` / `[WLE-UART] ...` (ANSI color codes removed) until a WBA line matches `--pass`.
5. Checks from the boot logs that the resets came through NRST (the NRST check below).

| Result | Output | Exit code |
| --- | --- | --- |
| A WBA line matches `--pass` | `[INFO] PASS: <line>` | 0 |
| A WBA line matches `--fail` | `[ERROR] FAIL: <line>` | 1 |
| Nothing within `--timeout` seconds after the reset | `[ERROR] timeout after N s waiting for: <regex>` | 1 |
| Setup problem (ST-Link, port, reset, pyserial) | `[ERROR] <reason>` | 1 |
| A reset did not come through NRST | `[ERROR] NRST check: ...` | 1 |

## The NRST check

`-hardRst` reports `Hard reset is performed` whether or not the ST-Link's NRST reaches the MCU, so the boot logs are checked instead, within 10 s of the resets:

| MCU | Passes on | Fails on |
| --- | --- | --- |
| WBA | The bootloader's `Reset reason: External NRST Reset` (`[INFO] NRST check: WBA reset reason External NRST`). | Another reason (e.g. `Software Reset`), or no reset reason at all. |
| WLE | The app's boot banner `Application name: ...` (`[INFO] NRST check: WLE rebooted`). | WLE log lines without the banner (the WLE kept running). A WLE log that stays silent (a build without logs) is only a warning. |

The pass line is reported once the check has its answer. `--no-nrst-check` skips it, e.g. for firmware without the sid_smartac bootloader. [sid_secure_prog](../sid_secure_prog/README.md) runs the same check on its resets (`NrstCheck`).

## The PASS line

sid_smartac's WBA app (`stm32wba5x/STM32_WPAN/App/app_sidewalk.c`) reports registration in two ways:

- `Sidewalk Device Registration done`: the device registered during this boot (`on_sidewalk_status_changed()`; printed only when the status changes to registered).
- `[SID-APP] Registration status: registered`: printed at every boot by `_init_sidewalk()`; a device registered before never prints the first line.

The default `--pass` regex accepts both: `Sidewalk Device Registration done|Registration status: registered`. Give your own regex to accept only a fresh registration.

| Option | Meaning |
| --- | --- |
| `--timeout S` | Seconds to wait after the reset (default 300). |
| `--pass REGEX`, `--fail REGEX` | WBA lines that end the wait (searched, not anchored). No `--fail` by default. |
| `--wle-sn`, `--wba-sn SN` | ST-Link serials. Optional. |
| `--wba-port`, `--wle-port PORT` | Serial ports, e.g. `/dev/ttyACM1` or `COM7`. Default: the ST-Link's VCP. |
| `--no-wle-log` | Do not open the WLE port. |
| `--no-reset` | Only wait, do not reset. With both ports given, no ST-Link is touched at all. |
| `--no-nrst-check` | Do not check from the boot logs that the resets came through NRST. |
| `--baud N` | Log baud rate (default 115200). |
| `--cli PATH`, `--freq KHZ` | As in stflash. |
| `--stlink-cache FILE` | Keep the ST-Link -> MCU mapping in FILE and reuse it while the same ST-Links are connected (with the resets only). Each reset checks the MCU's `Device ID`; a wrong cached mapping is detected again. |
| `--rescan` | Forget the `--stlink-cache` mapping first. |

## Python

A package, like the other tools here. Put `smac_tools/run_ui/tools` on `sys.path` (or `PYTHONPATH`):

```python
import sys
sys.path.insert(0, "smac_tools/run_ui/tools")
import sid_reg_wait

try:
    line = sid_reg_wait.wait_registration(timeout=300)
except sid_reg_wait.SidRegWaitError as e:
    print(f"not registered: {e}")
```

`wait_registration()` takes the CLI options as keyword arguments (`pass_re`, `fail_re`, `wle_sn`, `wba_port`, `wle_log`, `reset`, ...), prints the same log as the CLI and returns the matching line. `find_port()`, `port_devices()`, `open_logs()` / `close_logs()`, `reset_device()`, `watch()` and `collect()` (all lines up to a WBA line matching a regex, plus a few more seconds; both take an optional `NrstCheck`) are the pieces it is built from; [sid_secure_prog](../sid_secure_prog/README.md) uses them too. `python3 -m sid_reg_wait ...`, run from `smac_tools/run_ui/tools`, is the CLI.

## Tests

```sh
python3 -m unittest discover -s smac_tools/run_ui/tools/sid_reg_wait/tests
```

The tests use a fake `STM32_Programmer_CLI` and fake serial ports, so they need neither hardware nor pyserial. Not yet tried on a station: check that the ST-Link VCP's USB serial number equals the ST-Link serial on your ST-Link model (expected for STLINK-V3); if not, give the ports explicitly.
