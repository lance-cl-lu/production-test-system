# SMAC factory stations

Each station is a window with one **Start** button and a PASS/FAIL panel. To open a station, run its launcher in
this folder: `.bat` on Windows, `.sh` on Linux. More detail is in [tools/run_ui/README.md](tools/run_ui/README.md)
and in the README of each tool under [tools/run_ui/tools/](tools/run_ui/tools/).

## Install (once per station PC)

- Python 3.10 or later, with tkinter (Linux: `apt install python3-tk`). On Windows, `python` must be on PATH.
- `pip install -r tools/run_ui/requirements.txt` (pyserial, PyNaCl).
- STM32CubeProgrammer (`STM32_Programmer_CLI`).
- For **SID secure programming** only: patch CubeProgrammer for WBA OTP writes. In
  `Data_Base/STM32_Prog_DB_0x492.xml`, find the block with `address="0x0BF90000"` and change
  `<Alignment>0x4</Alignment>` to `0x10`. A CubeProgrammer update undoes the patch, and the station refuses to run
  without it. See [tools/run_ui/tools/sid_secure_prog/README.md](tools/run_ui/tools/sid_secure_prog/README.md).
- Two ST-Links per station, one on the WLE and one on the WBA, with NRST wired.

## Stations

**Pick the launcher that matches the board's HW revision** (2.0.2 or 2.0.3). All stations read their firmware,
the sign key and the SPI NOR images from the `images/` folder.

| Launcher | What it does | Images |
| --- | --- | --- |
| `smac_mfg_hw_2_0_2` | Writes the SMAC mfg data (sensor ICs + scanned label), then erases and programs WLE + WBA (debug WBA app) | `wle_boot_release_hw_2_0_2`, `wle_app_release_logs_hw_2_0_2`, `wba_boot_release`, `wba_app_debug_ble` |
| `smac_mfg_hw_2_0_3` | Same as above, for HW 2.0.3 | `wle_boot_release_hw_2_0_3`, `wle_app_release_logs_hw_2_0_3`, `wba_boot_release`, `wba_app_debug_no_ble` |
| `sid_registration` | Resets the device and waits up to 5 min for the Sidewalk registration (any HW) | none |
| `sid_secure_prog_hw_2_0_2` | Writes the release images, the sign key into WBA OTP, then RDP level 1 on both MCUs | `wle_boot_release_hw_2_0_2`, `wle_app_release_hw_2_0_2`, `wba_boot_release`, `wba_app_release_ble`, `sign_key_pub.pem`, `nor_flash_image_hw_2_0_2.bin` |
| `sid_secure_prog_hw_2_0_3` | Same as above, for HW 2.0.3 | `wle_boot_release_hw_2_0_3`, `wle_app_release_hw_2_0_3`, `wba_boot_release`, `wba_app_release_no_ble`, `sign_key_pub.pem`, `nor_flash_image_hw_2_0_3.bin` |
| `hvf_flashing` | Programs the HVF firmware on WLE + WBA | `WLE_smac_stm32wle5`, `WBA_smac_stm32wba5` |
| `sid_diag_flashing` | Programs the sid_diagnostics firmware on WLE + WBA | `sid_diagnostics_stm32wl55`, `sid_diagnostics_stm32wba55` |

**SID secure programming cannot be undone.** OTP is write-once. Going from RDP level 1 back to 0 erases the
device, including the Sidewalk registration and the mfg data. Before production, try new images on a bench board.

The SID secure programming station checks its files before it touches the device. To run only that check, with no
hardware attached:

```sh
python3 tools/run_ui/tools/sid_secure_prog/sid_secure_prog.py --check-only \
    --wle-boot images/wle_boot_release_hw_2_0_3.hex --wle-app images/wle_app_release_hw_2_0_3.hex \
    --wba-boot images/wba_boot_release.hex --wba-app images/wba_app_release_no_ble.hex \
    --sign-key images/sign_key_pub.pem --ext-flash images/nor_flash_image_hw_2_0_3.bin
```

## Station settings

The JSON configs are in `tools/run_ui/stations_config/<station>/`. The two HW configs are `config_hw_2_0_2.json` and
`config_hw_2_0_3.json`. In every config, `"cwd"` points at the `images/` folder, and the file names in `"args"`
are relative to it. To ship new firmware, replace the file in `images/` and keep the same name. The window re-reads
its config on every Start. To add an option to the tool, such as an SWD frequency (`"--freq", "1000"`), add it to
`"args"` in the config.
