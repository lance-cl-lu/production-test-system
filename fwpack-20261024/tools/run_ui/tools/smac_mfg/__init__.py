"""smac_mfg as a package: put smac_tools/run_ui/tools on sys.path, then `import smac_mfg`.

  import smac_mfg
  result = smac_mfg.program("wle_boot.hex", "wle_app.hex", "wba_boot.hex", "wba_app.hex", ["LPS22", "BME69X"],
                            "1A-2B3C4D")

See smac_mfg_flash.py (the CLI) and README.md.
"""

from .smac_mfg_flash import MfgFlashError, main, program, validate
# from the sibling gen_smac_mfg tool, e.g. to build a UI or check a label
from .smac_mfg_flash import gen_smac_mfg as _gen

IC_SENSOR_BITS = _gen.IC_SENSOR_BITS
LABEL_RE = _gen.LABEL_RE
FACTORY_DATA_ADDRESS = _gen.FACTORY_DATA_ADDRESS
build_factory_data = _gen.build_factory_data
parse_ic_names = _gen.parse_ic_names

__all__ = ["program", "validate", "main", "MfgFlashError", "IC_SENSOR_BITS", "LABEL_RE", "FACTORY_DATA_ADDRESS",
           "build_factory_data", "parse_ic_names"]
