"""combine_binaries as a package: put smac_tools/run_ui/tools on sys.path, then `import combine_binaries`.

  import pathlib, combine_binaries
  entries = combine_binaries.parse_inputs(["boot.hex", "app.hex", "data.bin", "0x0803F800"])
  combine_binaries.combine(entries, pathlib.Path("out.hex"))

See combine_binaries.py (the CLI) and README.md.
"""

from .combine_binaries import (InputError, coalesce_ranges, combine, main, merge_ihex, parse_ihex_ranges,
                               parse_inputs, print_memory_map)

__all__ = ["combine", "parse_inputs", "merge_ihex", "parse_ihex_ranges", "coalesce_ranges", "print_memory_map",
           "InputError", "main"]
