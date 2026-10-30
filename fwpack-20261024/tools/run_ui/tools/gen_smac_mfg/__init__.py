"""gen_smac_mfg as a package: put smac_tools/run_ui/tools on sys.path, then `import gen_smac_mfg`.

  import gen_smac_mfg
  data = gen_smac_mfg.build_factory_data(gen_smac_mfg.parse_ic_names(["LPS22", "BME69X"]), "1A-2B3C4D")

See gen_smac_mfg.py (the CLI) and README.md.
"""

from .gen_smac_mfg import (FACTORY_DATA_ADDRESS, FACTORY_DATA_SIZE, IC_SENSOR_BITS, LABEL_RE, InvalidEnvSensorsMapError,
                           InvalidIcNameError, InvalidLabelError, build_factory_data, encode_label, main,
                           parse_env_sensors_map, parse_ic_names)

__all__ = ["IC_SENSOR_BITS", "LABEL_RE", "FACTORY_DATA_ADDRESS", "FACTORY_DATA_SIZE", "build_factory_data",
           "parse_ic_names", "parse_env_sensors_map", "encode_label", "InvalidLabelError", "InvalidEnvSensorsMapError",
           "InvalidIcNameError", "main"]
