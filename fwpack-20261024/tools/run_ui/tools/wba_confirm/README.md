# wba_confirm

Adds the "confirmed" app validity marker to a WBA image (bootloader + app, Intel HEX). With `--wle` it also adds the bootloader metadata (see [below](#bootloader-metadata)). Standard library only, plus the sibling [combine_binaries](../combine_binaries/README.md).

```sh
smac_tools/run_ui/tools/wba_confirm/wba_confirm.py wba.hex --wle wle.hex -o wba_confirmed.hex
```

## Why

The WBA bootloader keeps a 16-byte validity marker per app:

| Marker | App state |
| --- | --- |
| all 1s | pending, so it runs on trial |
| `7AC3F91E D45E8B20 31B7C4DA E9A0625F` | confirmed |
| all 0s | rejected |

**Trial:** the app confirms itself only once a Sidewalk link connects. After 3 boots without that, the bootloader rejects it and reinstalls the factory container from the SPI NOR.

**Why programmed apps run on trial:** the marker section is NOLOAD, so a built image never contains it. An app programmed over SWD therefore runs on trial. A device that goes through several stations, each of which resets it, would be rolled back to the factory image.

**What this tool does:** it writes the marker already confirmed, as a factory install does (`app_wba_set_valid()`). The marker's address is the second word of the app's OTA header at 0x08012188. The marker is merged into the image, so the result is one file, written in one go.

`smac_mfg` (SMAC MFG station) and `sid_secure_prog` (SID secure programming station) both use it, with `--wle`.

## Bootloader metadata

A factory install also leaves two lines of bootloader metadata. They are NOLOAD too, and the stations' erase removes them. Without them the bootloader logs `[WARNING] metadata.c:306 err=15` (no installed container version) on every boot, and on the first boot `[ERROR] metadata.c:68` (no app implementation; it then writes SID). With `--wle WLE.hex`, the WLE image going onto the same device, the tool adds both lines as the bootloader itself writes them (16-byte lines, little-endian words):

| Address | Line | Content |
| --- | --- | --- |
| 0x0800E020 | OTA status page, installed container version | `C0DEBABE FEEDFACE 02AC0DE1 <version>` |
| 0x08010000 | AIM_META, app implementation | `5EEDFEE1 DEADF00D 999AABB3 00000000` (SID) |

`<version>` is the WBA app version plus the WLE app version, each packed `major<<24 | minor<<16 | patch<<8 | build`. That is how the bootloader checks a factory container against the installed one, and how `smac_tools/container/container.py` sets a container's version. So it equals the version of a SID factory container built from the same apps. The versions come from:
- **WBA:** the OTA header bytes at 0x08012190;
- **WLE:** `verfw` in the info block at the WLE app start, 0x08008800 (magic 0xC0FEB00B, `verfw` at offset 33).

The rest of the OTA status page (trial counter, install status) stays erased, which the bootloader reads as no trials and no install in progress.

## Checks

- The image has the app's OTA header at 0x08012188.
- The marker address is a 16-byte flash word below MFG_DATA (0x080FE000). `marker_address(..., limit=)` narrows this, e.g. to the area a station erases.
- The image has no data at the marker address.
- With `--wle`: the WLE image has its info block, the version sum fits 32 bits, and the image has no data at the metadata lines, which also lie below the limit, and the validity marker is not at one of them.

A failed check prints `[ERROR] <reason>` and exits with 1.

## Python

A package, like the other tools here. Put `smac_tools/run_ui/tools` on `sys.path` (or `PYTHONPATH`):

```python
import wba_confirm

marker = wba_confirm.confirm("wba.hex", "wba_confirmed.hex", wle_hex="wle.hex")  # marker address; raises WbaConfirmError
```

It also exports the pieces: `marker_address(segments, limit=)`, `metadata(wba_segments, wle_segments, limit=)` (the checked metadata lines), `container_version()`, `wba_version()`, `wle_version()`, `describe_metadata()`, the Intel HEX helpers `read_hex()`, `memory()`, `covered()`, `write_hex()`, and `CONFIRMED_MARKER`, `APP_HEADER`. `python3 -m wba_confirm ...`, run from `smac_tools/run_ui/tools`, is the CLI.

## Tests

```sh
python3 -m unittest discover -s smac_tools/run_ui/tools/wba_confirm/tests
```
