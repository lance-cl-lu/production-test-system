#!/bin/sh
# HVF FW programming
cd "$(dirname "$0")" || exit 1
exec python3 tools/run_ui/run_ui.py tools/run_ui/stations_config/hvf_flashing_station/config.json
