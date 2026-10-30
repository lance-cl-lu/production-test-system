"""wba_confirm as a package: put smac_tools/run_ui/tools on sys.path, then `import wba_confirm`.

  import wba_confirm
  marker = wba_confirm.confirm("wba.hex", "wba_confirmed.hex", wle_hex="wle.hex")

See wba_confirm.py (the CLI) and README.md.
"""

from .wba_confirm import (AIM_META, APP_HEADER, CONFIRMED_MARKER, CONTAINER_VERSION_LINE, FLASH_WORD, WBA_MFG_DATA,
                          WbaConfirmError, confirm, container_version, covered, describe_metadata, main,
                          marker_address, memory, metadata, metadata_lines, read_hex, version_str, wba_version,
                          wle_version, write_hex)

__all__ = ["confirm", "marker_address", "metadata", "metadata_lines", "container_version", "wba_version",
           "wle_version", "describe_metadata", "version_str", "read_hex", "memory", "covered", "write_hex", "main",
           "WbaConfirmError", "CONFIRMED_MARKER", "APP_HEADER", "CONTAINER_VERSION_LINE", "AIM_META", "FLASH_WORD",
           "WBA_MFG_DATA"]
