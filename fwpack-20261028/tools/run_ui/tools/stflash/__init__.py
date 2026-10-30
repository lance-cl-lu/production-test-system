"""stflash as a package: put smac_tools/run_ui/tools on sys.path, then `import stflash`.

  import stflash
  result = stflash.flash(wle_fw="wle.hex", wba_fw="wba.hex")   # {"WLE": True, "WBA": True}

See stflash.py (the CLI) and README.md.
"""

from . import stlink
from .stflash import (DEVICE_IDS, MCUS, Job, Probe, StFlashError, find_cli, flash, list_connected,
                      main, make_jobs)

__all__ = ["flash", "list_connected", "make_jobs", "find_cli", "main", "StFlashError", "Job", "Probe", "MCUS", "stlink",
           "DEVICE_IDS"]
