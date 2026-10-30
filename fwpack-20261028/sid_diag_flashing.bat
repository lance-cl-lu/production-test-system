@echo off
rem SID diagnostics FW programming
cd /d "%~dp0"
python tools\run_ui\run_ui.py tools\run_ui\stations_config\sid_diag_flashing_station\config.json
if errorlevel 1 pause
