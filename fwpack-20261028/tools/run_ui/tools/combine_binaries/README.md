# combine_binaries

Merges ELF, Intel HEX and raw binary images into one Intel HEX file, e.g. a bootloader, an application and a data blob into a single image to flash. Standard library only, plus `objcopy` for ELF and `.bin` inputs.

```sh
smac_tools/run_ui/tools/combine_binaries/combine_binaries.py wle_boot.hex wle_app.hex smac_mfg.bin 0x0803F800 -o wle.hex
```

- The input type comes from the extension: `.elf`, `.hex` / `.ihex`, `.bin`.
- A `.bin` has no addresses of its own, so it must be followed by its load address in hex.
- `.hex` inputs are used as they are. `.elf` and `.bin` inputs are converted with `arm-none-eabi-objcopy` (preferred) or `objcopy`, which must be on PATH. Set `ARM_NONE_EABI_OBJCOPY` to its full path if needed.
- Without `-o`, the output is named after the inputs, with dots replaced by underscores: `wle_boot_hex_wle_app_hex_smac_mfg_bin.hex`.
- The merge is textual: the inputs' records are concatenated in order, each input preceded by an extended-address reset record (so an input with no base record of its own is read at base 0), and one end-of-file record at the end. An input with lines after its own end-of-file record is refused: a reader of that file stops at the record, so those lines would otherwise reach the merged image unseen. Overlapping inputs are not detected; the caller keeps them apart.
- The tool prints the memory sections of the result and the gaps between them. Errors print `[ERROR] ...` and exit with 1.

## Python

A package, like the other tools here. Put `smac_tools/run_ui/tools` on `sys.path` (or `PYTHONPATH`):

```python
import sys
from pathlib import Path
sys.path.insert(0, "smac_tools/run_ui/tools")
import combine_binaries

entries = combine_binaries.parse_inputs(["wle_boot.hex", "wle_app.hex", "smac_mfg.bin", "0x0803F800"])
text = combine_binaries.combine(entries, Path("wle.hex"))      # raises combine_binaries.InputError
sections = combine_binaries.coalesce_ranges(combine_binaries.parse_ihex_ranges(text))
```

Exports `parse_inputs()`, `combine()`, `merge_ihex()`, `parse_ihex_ranges()`, `coalesce_ranges()`, `print_memory_map()`, `InputError` and `main(argv)`. `python3 -m combine_binaries ...`, run from `smac_tools/run_ui/tools`, is the CLI.

## Tests

```sh
python3 -m unittest discover -s smac_tools/run_ui/tools/combine_binaries/tests
```

The `.bin` test needs `objcopy` on PATH and skips otherwise.
