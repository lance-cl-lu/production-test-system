# run_ui

`run_ui` is a station window with one button. It runs a backend tool that is set up in a JSON file. The window itself uses the standard library only (tkinter).

## Install

Python 3.10 or later, then the Python packages the tools need:

```sh
pip install -r smac_tools/run_ui/requirements.txt
```

[requirements.txt](requirements.txt) also lists what pip cannot install: tkinter (`apt install python3-tk` on Debian/Ubuntu), STM32CubeProgrammer for the flashing tools, and `objcopy` (binutils) for combine_binaries.

```
+--------------------------------------------+
|            HVF FW programming              |   <- "title"
|  +------------+   +--------------------+   |
|  |   Start    |   |   status (color)   |   |
|  +------------+   +--------------------+   |
|  [ backend output log ]                    |   <- "show_log"
+--------------------------------------------+
```

When you press **Start**:
- The tool runs `backend` with `args`.
- The button is disabled while the backend runs.
- The panel follows the backend's output through the `progress` rules.
- When the backend exits, the panel shows **PASS** for exit code 0 and **FAIL** otherwise.

The JSON is re-read on every Start, so you can edit it without restarting the window.

```sh
smac_tools/run_ui/run_ui.py stations_config/hvf_flashing_station/config.json   # a station config given as an argument
smac_tools/run_ui/run_ui.py --config station.json
smac_tools/run_ui/run_ui.py                                    # uses config.json next to the script, if there is one
```

## Stations

Each station is a folder in `stations_config/` with a `config.json` and the firmware images it programs. The backend tools live in `tools/`: all stations flash through [stflash](tools/stflash/README.md), the first two run it as their backend, `smac_mfg_station` through [smac_mfg](tools/smac_mfg/README.md), which imports it. `tools/` also holds [gen_smac_mfg](tools/gen_smac_mfg/README.md), [combine_binaries](tools/combine_binaries/README.md) (used by smac_mfg) and [sid_reg_wait](tools/sid_reg_wait/README.md) (reset the device and wait for the Sidewalk registration) and [sid_secure_prog](tools/sid_secure_prog/README.md) (static images, OTP sign key, RDP 1). [wba_confirm](tools/wba_confirm/README.md) adds the confirmed app validity marker and the bootloader metadata to a WBA image (used by smac_mfg and sid_secure_prog).

| Folder | Programs | Images to put in the folder |
| --- | --- | --- |
| `stations_config/hvf_flashing_station/` | WLE and WBA | `WLE_smac_stm32wle5.hex`, `WBA_smac_stm32wba5.hex` |
| `stations_config/sid_diag_flashing_station/` | WLE and WBA (sid_diagnostics) | `sid_diagnostics_stm32wl55.hex`, `sid_diagnostics_stm32wba55.hex` |
| `stations_config/smac_mfg_station/` | SMAC manufacturing data + WLE and WBA, through [smac_mfg_flash](tools/smac_mfg/README.md); erases the WLE completely and the WBA except its Sidewalk MFG_DATA page first; the WBA app is written already confirmed (no trial, no factory rollback at later stations); uses [inputs](#inputs) for the sensor ICs and the scanned label | WLE and WBA bootloader + app, as named in its `config.json` (`wle_boot_*.hex`, `wle_app_*.hex`, `wba_boot.hex`, `wba_app.hex`) |
| `stations_config/sid_do_registration_station/` | Nothing: resets the WLE and WBA and waits (5 min, `--timeout` in the JSON) for the Sidewalk registration on the WBA log, through [sid_reg_wait](tools/sid_reg_wait/README.md). Needs pyserial, see [Install](#install) | none |
| `stations_config/sid_secure_programming_station/` | Static WLE and WBA images (keeping the SMAC mfg data and the Sidewalk registration), the sign key into WBA OTP after checking the boot log against the key and the SPI NOR factory image, then RDP level 1 on both MCUs, through [sid_secure_prog](tools/sid_secure_prog/README.md). OTP and RDP cannot be undone. Needs pyserial, PyNaCl and a patched STM32CubeProgrammer, see its README | WLE and WBA bootloader + app (merged by the station), `sign_key_pub.pem`, `spi_flash_factory.bin`, as named in its `config.json` |

The `.hex` images, key files (`.pem`) and SPI flash images are not in git (`.gitignore`); copy them into the station folder before use.

## Config

An example, based on [stations_config/hvf_flashing_station/config.json](stations_config/hvf_flashing_station/config.json) with a WLE image added:

```json
{
  "title": "HVF FW programming",
  "backend": "../../tools/stflash/stflash.py",
  "args": ["--wle-fw", "wle.hex", "--wba-fw", "wba.hex"],
  "show_log": true,
  "states": {
    "idle":    {"text": "Ready",    "color": "gray"},
    "running": {"text": "Running…", "color": "gold"},
    "pass":    {"text": "PASS",     "color": "green"},
    "fail":    {"text": "FAIL",     "color": "red"}
  },
  "progress": [
    {"match": "^\\[INFO\\] \\[WLE\\]", "text": "WLE: programming…", "color": "dodger blue"},
    {"match": "^\\[ERROR\\] (.*)",     "text": "Error:\n{1}",       "color": "orange"}
  ]
}
```

| Key | Required | Meaning |
| --- | --- | --- |
| `title` | yes | Text above the button and panel. Also the window title. |
| `backend` | yes | Tool to run. A relative path is resolved from the JSON's folder first, then from `PATH`. A `.py` backend runs with the same Python as the UI. |
| `args` | yes | Arguments, as a list of strings with one item per argument. They are passed as is. |
| `cwd` | no | Working directory for the backend, relative to the JSON's folder. The default is the JSON's folder, so relative file names in `args` are next to the JSON. |
| `show_log` | no | Show the output pane (default `true`). |
| `states` | no | `text`/`color` for `idle`, `running`, `pass` and `fail`. Missing keys keep the defaults shown above. |
| `progress` | no | Rules checked against each output line, in order. The first `match` (a Python regex) that matches sets the panel. In `text`, `{1}`, `{2}`… are regex groups, `{line}` is the whole line, and `{{ }}` give literal braces. |

Colors can be any Tk color name (`gray`, `green`, `red`, `gold`, `orange`, `dodger blue`…) or `#rrggbb`. The text on the panel turns black or white depending on the background.

| `inputs` | no | Extra controls whose values go into `args`, see [Inputs](#inputs). |

Notes:
- **Config errors:** a bad JSON file, a missing backend, a bad regex or an unknown color is shown in red on the panel. Fix the file and press Start again.
- **Final state:** set only by the exit code, never by a rule. On failure the panel shows the exit code, and the reason is in the log.
- **Closing while the backend runs:** the window asks first, then stops the backend together with every process it started (e.g. a running `STM32_Programmer_CLI`) and waits until they are gone; anything still running after 3 s is killed.

## Inputs

`inputs` adds controls above the Start button. Their values replace placeholders in `args`, and Start is enabled only when every configured input has a value.

```json
"args": ["--ics", "{ics}", "--label", "{label}"],
"inputs": {
  "ics":   {"label": "Sensor ICs", "choices_from": {"file": "../../tools/gen_smac_mfg/gen_smac_mfg.py", "name": "IC_SENSOR_BITS"}},
  "label": {"label": "Label",      "pattern_from": {"file": "../../tools/gen_smac_mfg/gen_smac_mfg.py", "name": "LABEL_RE"}}
}
```

| Input | Control | Placeholder | Keys |
| --- | --- | --- | --- |
| `ics` | The selected names and a **Select…** button that opens a checkbox list. At least one must be selected. The selection lasts until the window closes. | An arg that is exactly `{ics}` becomes one arg per selected name, in list order. | `choices` (list of names) or `choices_from`; `label` (default `ICs`) |
| `label` | A large label display, filled by a barcode/QR scanner. | `{label}` anywhere in an arg is replaced by the scanned text. | `pattern` (regex) or `pattern_from`; `label` (default `Label`) |

- `choices_from` / `pattern_from` take `{"file": ..., "name": ...}`: the named object is read from that Python file (path relative to the JSON). A dict gives its keys as the choices; a regex can be a string or a compiled pattern. This keeps the tool that consumes the values the only place that defines them.
- **Scanner:** a USB scanner in keyboard (HID) mode types the code; the window collects the keys while it has focus, and Enter or Tab ends the code. Escape drops a partial code. The whole code must match the pattern; an invalid code is shown in red and Start stays disabled. Typing a code and pressing Enter works too.
- **One scan per device:** Start uses the current label and clears it, so the next device needs a new scan. A code scanned while the backend runs is kept for the next Start.
- A placeholder without its input, or an input that no arg uses, is a config error.

## Tests

```sh
python3 -m unittest discover -s smac_tools/run_ui/tests
```
