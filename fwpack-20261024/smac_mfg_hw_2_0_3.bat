@echo off
rem SMAC MFG programming, HW 2.0.3
cd /d "%~dp0"
python tools\run_ui\run_ui.py tools\run_ui\stations_config\smac_mfg_station\config_hw_2_0_3.json
if errorlevel 1 pause
