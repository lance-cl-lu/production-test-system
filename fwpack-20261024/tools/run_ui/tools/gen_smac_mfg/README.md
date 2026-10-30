# gen_smac_mfg

Builds `smac_mfg.bin`, the sid_smartac WLE manufacturing data: the 16-byte `factory_data_internal_t` the WLE app reads from flash at 0x0803F800 (`.factory_data`, start of `PERMANENT_DATA` in `STM32WLE5CCUX_FLASH.ld`). The section is NOLOAD and not part of the app image, so the file is flashed separately, e.g. merged into the WLE image by [combine_binaries](../combine_binaries/README.md) as [smac_mfg](../smac_mfg/README.md) does. Standard library only.

```sh
smac_tools/run_ui/tools/gen_smac_mfg/gen_smac_mfg.py -i LPS22 ENS21X BME69X -l 1A-2B3C4D -o smac_mfg.bin
```

| Option | Meaning |
| --- | --- |
| `-i`, `--ics IC [IC ...]` | Sensor ICs on the board; builds the sensor map from them. Not with `-m`. |
| `-m`, `--env-sensors-map HEX` | The sensor map as a hex value (e.g. `7FF`). Not with `-i`. |
| `-l`, `--label LABEL` | Back label, `XX-XXXXXX` or `XXXXXXXX` (hex digits, case-insensitive). |
| `-o`, `--output FILE` | Output file (default: `smac_mfg.bin` next to the script). |

A field that is not given is left unpopulated: data and inverted copy are both 0xFF, like erased flash, so the firmware reports it as missing.

## IC names

One name per sensor family, because the firmware gives every part of a family the same sensor IDs (`sampler_sensor_list.c`):

| IC | Sensor IDs (bits) |
| --- | --- |
| `LPS22` | TEMP_1 (0), PRESS_1 (8). One driver for LPS22DF/HH/HB, told apart at runtime. |
| `ENS21X` | TEMP_2 (1), RH_1 (5). Any of ENS210/211/212/213/215. |
| `SHT4X` | TEMP_2 (1), RH_1 (5): the same as ENS21X. Both are alternative parts for the same board position; the firmware uses SHT4x if it probes, else ENS21x. |
| `BME69X` | TEMP_3 (2), RH_2 (6), PRESS_2 (9). |

The external sensors (2SMPB, SHTC3) have no IC name and can only be set with `-m`.

## Layout

| Bytes | Field |
| --- | --- |
| 0-3 | label: 8 hex digits, two per byte, first digit in the high nibble of byte 0 |
| 4-7 | label, each byte inverted |
| 8-11 | env_sensors_map, uint32 little-endian |
| 12-15 | env_sensors_map, inverted |

`factory_data_get()` returns a field only if its inverted copy matches. The label packing is this tool's choice: neither `factory_data.h` nor `INFO_FRAME_SPEC.md` defines it, and it has not yet been checked against a reference device.

## Python

A package, like the other tools here. Put `smac_tools/run_ui/tools` on `sys.path` (or `PYTHONPATH`):

```python
import sys
sys.path.insert(0, "smac_tools/run_ui/tools")
import gen_smac_mfg

data = gen_smac_mfg.build_factory_data(gen_smac_mfg.parse_ic_names(["LPS22", "BME69X"]), "1A-2B3C4D")  # 16 bytes
```

Exports `IC_SENSOR_BITS`, `LABEL_RE`, `FACTORY_DATA_ADDRESS`, `FACTORY_DATA_SIZE`, `build_factory_data()`, `parse_ic_names()`, `parse_env_sensors_map()`, `encode_label()`, the `Invalid*Error` exceptions and `main(argv)`. `python3 -m gen_smac_mfg ...`, run from `smac_tools/run_ui/tools`, is the CLI.

## Tests

```sh
python3 -m unittest discover -s smac_tools/run_ui/tools/gen_smac_mfg/tests
```
