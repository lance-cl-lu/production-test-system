#!/bin/sh
# SID secure programming, HW 2.0.2
cd "$(dirname "$0")" || exit 1
exec python3 tools/run_ui/run_ui.py tools/run_ui/stations_config/sid_secure_programming_station/config_hw_2_0_2.json
