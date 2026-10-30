# smac_mfg

Programs one sid_smartac device with its SMAC manufacturing data and the WLE and WBA firmware. It is the backend of the `smac_mfg_station` [run_ui](../../README.md) station, and chains three sibling tools in `smac_tools/run_ui/tools/`: [gen_smac_mfg](../gen_smac_mfg/README.md), [combine_binaries](../combine_binaries/README.md) and [stflash](../stflash/README.md). Standard library only.

## smac_mfg_flash.py

```sh
smac_tools/run_ui/tools/smac_mfg/smac_mfg_flash.py --wle-boot wle_boot.hex --wle-app wle_app.hex \
                                                   --wba-boot wba_boot.hex --wba-app wba_app.hex \
                                                   --ics LPS22 BME69X --label 1A-2B3C4D
```

1. [gen_smac_mfg.py](../gen_smac_mfg/README.md) `-i <ICs> -l <label>` writes `smac_mfg.bin`.
2. [combine_binaries.py](../combine_binaries/README.md) merges the WLE bootloader, the WLE app and `smac_mfg.bin` (at 0x0803F800) into one WLE hex.
3. [combine_binaries.py](../combine_binaries/README.md) merges the WBA bootloader and the WBA app into one WBA hex, and [wba_confirm](../wba_confirm/README.md) adds the confirmed app validity marker. The app then does not run on trial: a device that goes through further stations (each resets it) is not rolled back to the factory container. wba_confirm also adds the [bootloader metadata](../wba_confirm/README.md#bootloader-metadata) that the erase in step 4 removes: the installed container version (WBA + WLE app version, read from the step 2 image) and the app implementation (SID). Without it the bootloader warns `metadata.c:306 err=15` on every boot.
4. [stflash](../stflash/README.md), imported as a package (`stflash.flash()`), erases and flashes the WLE hex, then the WBA hex (see the erase note below).

Each step starts with an `[INFO] [STEP n/4] ...` line, and the tools' own output follows. The first failing step stops the run with `[ERROR] <step> failed (exit N)` and that exit code. Bad inputs (missing file, unknown IC, malformed label) are reported before any step runs.

| Option | Meaning |
| --- | --- |
| `--wle-boot`, `--wle-app FILE` | WLE bootloader and application images (.hex or .elf). |
| `--wba-boot`, `--wba-app FILE` | WBA bootloader and application images (.hex or .elf). |
| `--ics IC [IC ...]` | Sensor ICs on the board: LPS22, ENS21X, SHT4X, BME69X (`IC_SENSOR_BITS` in gen_smac_mfg, case-insensitive). |
| `--label LABEL` | Back label, `XX-XXXXXX` or `XXXXXXXX` (hex digits). |
| `--out-dir DIR` | Keep the combined hex files (`wle_<label>.hex`, `wba_<label>.hex`) here. By default they are deleted. |
| `--wle-sn`, `--wba-sn`, `--mode`, `--freq`, `--cli`, `--dry-run` | Passed to stflash. |

The images are whatever the station is given. For the current station tests they are the builds with logging; production images without logs replace them later, with no tool change.

Notes:
- combine_binaries converts `smac_mfg.bin` (and any ELF input) with `objcopy`, which must be on PATH. Using .hex images for the bootloader and app avoids depending on objcopy for anything else.
- **Everything else is erased.** Before writing, the WLE is mass-erased (`-e all`), and the WBA has every page erased except MFG_DATA, the Sidewalk manufacturing data in page 127 at 0x080FE000 (`-e 0 .. 126`). That includes the WLE NVM, the WBA bootloader state, LittleFS (Sidewalk registration) and BLE NVM. A board left half-programmed by an earlier failed run is reprogrammed from scratch. The combined WLE hex brings the SMAC mfg data back.
- The label nibble packing in gen_smac_mfg has not yet been checked against a reference device (see its [README](../gen_smac_mfg/README.md)).

## Python

`smac_mfg/` is also a package, like [stflash](../stflash/README.md). Put `smac_tools/run_ui/tools` on `sys.path` (or `PYTHONPATH`) and import it:

```python
import sys
sys.path.insert(0, "smac_tools/run_ui/tools")
import smac_mfg

try:
    result = smac_mfg.program("wle_boot.hex", "wle_app.hex", "wba_boot.hex", "wba_app.hex", ["LPS22", "BME69X"],
                              "1A-2B3C4D")
except smac_mfg.MfgFlashError as e:
    print(f"failed: {e} (exit code {e.exit_code})")
```

| Name | Meaning |
| --- | --- |
| `program(wle_boot, wle_app, wba_boot, wba_app, ics, label, *, out_dir=None, dry_run=False, wle_sn, wba_sn, mode, freq, cli)` | The four steps, same as the CLI and with the same log. Returns stflash's `{"WLE": True, "WBA": True}`. Raises `MfgFlashError` on the first failing check or step; its `exit_code` is what the CLI would exit with. |
| `validate(wle_boot, wle_app, wba_boot, wba_app, ics, label, out_dir=None)` | Only the input checks, nothing runs. |
| `IC_SENSOR_BITS`, `LABEL_RE`, `FACTORY_DATA_ADDRESS`, `build_factory_data()`, `parse_ic_names()` | Re-exported from the [gen_smac_mfg](../gen_smac_mfg/README.md) package, e.g. to build a UI or check a label. |

`python3 -m smac_mfg ...`, run from `smac_tools/run_ui/tools`, is the same as running `smac_mfg/smac_mfg_flash.py`.

## Tests

```sh
python3 -m unittest discover -s smac_tools/run_ui/tools/smac_mfg/tests
```

The end-to-end test runs all three steps with `--dry-run` and checks the combined WLE hex byte by byte. It needs `objcopy` and `true` on PATH, and skips otherwise.
