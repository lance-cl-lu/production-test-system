#!/bin/sh
# SID diagnostics FW programming
cd "$(dirname "$0")" || exit 1
exec python3 tools/run_ui/run_ui.py tools/run_ui/stations_config/sid_diag_flashing_station/config.json
