# stflash

Flash a `.hex` or `.bin` to the WLE and/or the WBA through ST-Link, using `STM32_Programmer_CLI`
(STM32CubeProgrammer) as the backend. Standard library only.

The tool doesn't know what an image is for. A `.bin` needs `--xxx-addr`, and a `.hex` must not have one.

## Usage

```sh
# which ST-Link is connected to which MCU
smac_tools/run_ui/tools/stflash/stflash.py --list

# one MCU; the ST-Link is detected automatically
smac_tools/run_ui/tools/stflash/stflash.py --wle-fw sid_smartac_stm32wle5.hex
smac_tools/run_ui/tools/stflash/stflash.py --wba-fw app.bin --wba-addr 0x08012000

# both MCUs; the WLE is flashed first, then the WBA
smac_tools/run_ui/tools/stflash/stflash.py --wle-fw wle.hex --wba-fw wba.hex

# explicit ST-Links
smac_tools/run_ui/tools/stflash/stflash.py --wle-sn 003A00213133510A37363734 --wle-fw wle.bin --wle-addr 0x08008800 \
                                           --wba-sn 0026003F3233511239363634 --wba-fw wba.hex

# print the commands without touching the hardware
smac_tools/run_ui/tools/stflash/stflash.py --dry-run --wle-fw wle.hex
```

`--inter-mcu-delay SECONDS` optionally waits between WLE and WBA. The HVF station sets it to one second.

| Option | Meaning |
| --- | --- |
| `--wle-fw` / `--wba-fw FILE` | Firmware for that MCU. This option enables the MCU. |
| `--wle-addr` / `--wba-addr ADDR` | Load address. Required for a `.bin`, not allowed for a `.hex`. |
| `--wle-erase` / `--wba-erase PAGES` | Erase before writing, in the same CLI run: `all` (mass erase) or flash pages, e.g. `0-126` or `0,1,5-8`. |
| `--wle-sn` / `--wba-sn SN` | ST-Link serial. Optional. |
| `--mode {UR,NORMAL,HOTPLUG}` | SWD connect mode for flashing. The default is `UR` with `reset=HWrst`, which needs NRST wired. `NORMAL` uses `reset=SWrst`. |
| `--freq KHZ` | SWD frequency (default 2000 kHz). |
| `--inter-mcu-delay SECONDS` | Wait between WLE and WBA flashing (default: no delay). |
| `--no-verify`, `--no-reset` | Skip `-v`, or skip `-rst` after writing. |
| `--cli PATH` | Path to `STM32_Programmer_CLI`. Otherwise the tool tries `$STM32_CUBEPROGRAMMER_CLI_BIN`, then `PATH`, then the default install directories. |

Without `--xxx-erase`, `-w` erases only the sectors it writes. Nothing else is erased.

## ST-Link detection

The tool runs `STM32_Programmer_CLI --list st-link`. It then connects to the ST-Links to read the target Device ID:
- `0x497` is the WLE.
- `0x492`, `0x4B0` and `0x4B2` are the WBA.

How it connects:
- It tries hot-plug first, which doesn't reset the target.
- If hot-plug fails, it retries with the `--mode` connect (under reset by default).

The ST-Links it connects to depend on the serials:
- **With a serial:** only that ST-Link is connected, and it must be on the right MCU. A WLE serial that points at the WBA is rejected before anything is written.
- **Without a serial:** every ST-Link is connected, and exactly one must report that MCU. If none or several do, the tool stops and lists what it found.

## Exit code

The exit code is 0 only if every requested MCU was flashed. A failure counts if the CLI returns non-zero or prints an `Error:` line. If the WLE fails, the WBA is still flashed, and a summary is printed at the end.

## Python

`stflash/` is also a package, so a script can call it directly instead of running the CLI. Put `smac_tools/run_ui/tools` on `sys.path` (or `PYTHONPATH`) and import it:

```python
import sys
sys.path.insert(0, "smac_tools/run_ui/tools")
import stflash

try:
    result = stflash.flash(wle_fw="wle.hex", wba_fw="wba.hex")   # {"WLE": True, "WBA": True}
except stflash.StFlashError as e:
    print(f"cannot flash: {e}")

for probe in stflash.list_connected():                          # like --list
    print(probe.sn, probe.mcu)
```

| Function | Meaning |
| --- | --- |
| `flash(wle_fw=None, wba_fw=None, *, wle_addr, wba_addr, wle_sn, wba_sn, wle_erase, wba_erase, mode="UR", freq, verify=True, reset=True, cli, dry_run=False)` | Same as the CLI options (`*_erase`: `"all"` or page numbers). Prints the same log as the CLI and returns `{mcu: ok}` for each MCU given; a failed write is `False`. Raises `StFlashError` for setup problems: bad arguments, `STM32_Programmer_CLI` not found, ST-Link missing or connected to the wrong MCU. |
| `list_connected(cli=None, mode="UR", freq=None)` | The connected ST-Links as `Probe` objects (`sn`, `board`, `mcu`, `device_id`, `device_name`, `error`). |
| `make_jobs(...)` | Only the argument checks of `flash()`, no hardware access. |

`python3 -m stflash ...`, run from `smac_tools/run_ui/tools`, is the same as running `stflash/stflash.py`.

## Shared ST-Link module (stlink.py)

The ST-Link handling lives in `stlink.py`, so other tools can use it without flashing anything (e.g. [sid_reg_wait](../sid_reg_wait/README.md)):

```python
from stflash import stlink

cli = stlink.find_cli()
probes = stlink.resolve(["WLE", "WBA"], cli=cli)      # {"WLE": Probe, "WBA": Probe}, ST-Links auto-detected
stlink.reset(cli, probes["WBA"].sn, "[WBA]")          # NRST reset, True on success
```

| Name | Meaning |
| --- | --- |
| `find_cli(path=None)` | `STM32_Programmer_CLI` lookup, as described under Usage. |
| `resolve(mcus, *, sns=None, cli, mode="UR", freq=None)` | Lists and identifies the ST-Links (connect only) and returns `{mcu: Probe}`. `sns` gives the serial for some MCUs; the others are auto-detected, as described under ST-Link detection. Prints one `[INFO] ST-Link ...` line per ST-Link. |
| `reset(cli, sn, prefix, freq=None)` | Hardware reset through NRST (`mode=HOTPLUG -hardRst`), output streamed under `prefix`. Needs NRST wired. |
| `program(cli, sn, path, prefix, *, erase_pages=None, verify=True, mode="UR", freq=None)` | Writes a `.hex`, first erasing the given flash pages, in one CLI run (`-e <pages> -w <file> -v`). |
| `read_memory(cli, sn, address, size)` | Reads target memory (`-u`), e.g. the WBA OTP. |
| `read_rdp(cli, sn)`, `set_rdp(cli, sn, value, prefix)` | RDP option byte through `-ob displ` / `-ob RDP=0x..`; `RDP_LEVEL_0` = 0xAA, `RDP_LEVEL_1` = 0xBB. |
| `otp_db_alignment(cli)` | The WBA OTP write alignment in CubeProgrammer's device database (must be 0x10 for OTP writes, see [sid_secure_prog](../sid_secure_prog/README.md#setup)). |
| `list_probes()`, `identify()`, `resolve_probes()`, `run_job()`, `connect_args()`, `Probe`, `StLinkError`, `DEVICE_IDS`, `MCUS` | The building blocks. |

`stflash.py` imports these and re-exports them, so `stflash.identify()` and friends still work; `StFlashError` is `StLinkError`.

## Tests

```sh
python3 -m unittest discover -s smac_tools/run_ui/tools/stflash/tests
```

The tests replace `STM32_Programmer_CLI` with a fake shell script, so they need no hardware.
